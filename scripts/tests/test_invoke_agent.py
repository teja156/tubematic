"""Unit tests for poll.py's invoke_agent() — command construction and the
post-run verdict.

invoke_agent had zero test coverage before TMDEV-63 (the exact argv and
dry-run's no-subprocess-call behavior were untested). Since TMDEV-73 the model
is a parameter rather than module state, and since TMDEV-90 so is the agent:
a GET /agents row, whose adapter (scripts/agent_adapters.py) builds the argv.
"""
import logging
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from unittest.mock import patch

import pytest

import poll

AGENT = {"id": "claude", "binary": "claude", "run_path": "/tmp/agent-ws", "models": ["opus"]}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(poll, "_setup_logging", lambda dry_run=False: None)
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/local/bin/claude")
    monkeypatch.setattr(poll, "resolve_agent_cwd", lambda agent: tmp_path)


def _result(stdout="", stderr="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)


def test_blank_model_leaves_argv_unchanged():
    """Regression guard: a run with no model gets the exact same command as
    before per-video models existed."""
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("do the thing", AGENT, dry_run=False)
    run.assert_called_once()
    args, kwargs = run.call_args
    assert args[0] == ["/usr/local/bin/claude", "-p", "do the thing", "--output-format", "json"]


def test_alias_model_appends_flag():
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("do the thing", AGENT, dry_run=False, model="opus")
    args, _ = run.call_args
    assert args[0] == ["/usr/local/bin/claude", "-p", "do the thing", "--output-format", "json", "--model", "opus"]


def test_full_model_id_passes_through_verbatim():
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("do the thing", AGENT, dry_run=False,
                           model="claude-sonnet-4-5-20250929")
    args, _ = run.call_args
    assert args[0] == [
        "/usr/local/bin/claude", "-p", "do the thing", "--output-format", "json", "--model", "claude-sonnet-4-5-20250929",
    ]


def test_runs_from_the_agents_own_workspace(tmp_path):
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("p", AGENT)
    assert run.call_args.kwargs["cwd"] == tmp_path


def test_an_agent_with_no_adapter_is_refused_without_running(caplog):
    caplog.set_level(logging.ERROR, logger=poll.log.name)
    with patch.object(poll, "_execute") as run:
        poll.invoke_agent("p", {**AGENT, "id": "openclaw"})
    run.assert_not_called()
    assert "No adapter for agent 'openclaw'" in caplog.text


def test_a_missing_binary_runs_nothing(monkeypatch):
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: None)
    with patch.object(poll, "_execute") as run:
        poll.invoke_agent("p", AGENT, model="opus")
    run.assert_not_called()


def test_dry_run_never_calls_subprocess_and_redacts_prompt(caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    with patch.object(poll, "_execute") as run:
        poll.invoke_agent("a very secret prompt body", AGENT, dry_run=True, model="opus")
    run.assert_not_called()
    logged = "\n".join(r.message for r in caplog.records)
    assert "a very secret prompt body" not in logged
    assert "--model opus" in logged


# ── resolve_agent_binary: re-resolved through PATH, never exec'd as stored ──

def test_resolve_agent_binary_goes_through_which(monkeypatch):
    monkeypatch.undo()  # the autouse stub replaced the real function
    with patch.object(poll.shutil, "which", return_value="/opt/bin/claude") as which:
        assert poll.resolve_agent_binary({"id": "claude", "binary": "/opt/bin/claude"}) \
            == "/opt/bin/claude"
    which.assert_called_once_with("/opt/bin/claude")


def test_resolve_agent_binary_logs_the_reinstall_command(monkeypatch, caplog):
    monkeypatch.undo()
    with patch.object(poll.shutil, "which", return_value=None):
        assert poll.resolve_agent_binary({"id": "claude", "binary": "/gone/claude"}) is None
    assert "--install-agent claude" in caplog.text


# ── Unusable model falls back to the CLI default (TMDEV-81 follow-up) ────────

@pytest.mark.parametrize("bad", ["two words", "--dangerously-skip-permissions", "  spaced out  "])
def test_an_argv_corrupting_model_is_dropped_not_passed(bad):
    """No --model flag means the agent CLI uses its own default — a working run
    instead of a broken invocation."""
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("prompt", AGENT, model=bad)
    cmd = run.call_args[0][0]
    assert "--model" not in cmd


@pytest.mark.parametrize("good,expected", [("opus", "opus"), ("  sonnet  ", "sonnet"),
                                           ("claude-opus-5", "claude-opus-5")])
def test_a_well_formed_model_is_passed_through_trimmed(good, expected):
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("prompt", AGENT, model=good)
    cmd = run.call_args[0][0]
    assert cmd[cmd.index("--model") + 1] == expected


def test_a_misspelled_but_well_formed_model_is_still_passed():
    """Deliberately not a pre-run catalog check. A bad name is caught after the
    run, from the agent's output — see the rejected-model tests below."""
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("prompt", AGENT, model="sonnett")
    assert "sonnett" in run.call_args_list[0][0][0]


# ── A rejected model is read from the output, never the exit code ────────────

# What the Claude CLI actually prints for an unknown model — and it exits 0.
_REJECTED = (
    '[claude-code:unrecognized_model] {"model":"sonnett","query_source":"sdk"}\n'
    "There's an issue with the selected model (sonnett). It may not exist or you "
    "may not have access to it.\n"
)


def test_a_rejected_model_logs_an_error_and_reruns_without_model(caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    with patch.object(poll, "_execute",
                      side_effect=[_result(stdout=_REJECTED), _result(stdout="done")]) as run:
        poll.invoke_agent("do the thing", AGENT, model="sonnett")
    assert run.call_count == 2
    assert run.call_args_list[0][0][0][-2:] == ["--model", "sonnett"]
    assert run.call_args_list[1][0][0] == ["/usr/local/bin/claude", "-p", "do the thing", "--output-format", "json"]
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("rejected model 'sonnett'" in m for m in errors)
    # The exit-0 "completed" line must not be claimed for the rejected run.
    assert sum("Agent completed (exit 0)" in r.getMessage() for r in caplog.records) == 1


def test_the_marker_on_stderr_is_caught_too():
    with patch.object(poll, "_execute",
                      side_effect=[_result(stderr=_REJECTED), _result()]) as run:
        poll.invoke_agent("p", AGENT, model="sonnett")
    assert run.call_count == 2


def test_a_clean_run_is_not_retried():
    with patch.object(poll, "_execute", return_value=_result(stdout="all good")) as run:
        poll.invoke_agent("p", AGENT, model="opus")
    assert run.call_count == 1


def test_no_model_and_a_marker_logs_an_error_without_retrying(caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    with patch.object(poll, "_execute", return_value=_result(stdout=_REJECTED)) as run:
        poll.invoke_agent("p", AGENT)
    assert run.call_count == 1
    assert any(r.levelno == logging.ERROR and "nothing to fall back from" in r.getMessage()
               for r in caplog.records)


def test_a_fallback_that_is_still_rejected_is_reported_not_looped(caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    with patch.object(poll, "_execute", return_value=_result(stdout=_REJECTED)) as run:
        poll.invoke_agent("p", AGENT, model="sonnett")
    assert run.call_count == 2
    assert any("still reports" in r.getMessage() for r in caplog.records)


@pytest.mark.parametrize("returncode", [0, 1])
def test_the_verdict_never_depends_on_the_exit_code(returncode):
    """Marker + any exit code → rejected; clean output + any exit code → not."""
    with patch.object(poll, "_execute",
                      side_effect=[_result(stdout=_REJECTED, returncode=returncode),
                                   _result()]) as run:
        poll.invoke_agent("p", AGENT, model="sonnett")
    assert run.call_count == 2
    with patch.object(poll, "_execute",
                      return_value=_result(stdout="fine", returncode=returncode)) as run:
        poll.invoke_agent("p", AGENT, model="opus")
    assert run.call_count == 1


# ── Effort, and the two-flag fallback ladder (TMDEV-106) ────────────────────

# What an older CLI that has never heard of the flag actually prints — and it
# exits non-zero having run nothing at all, the opposite shape to the model
# case above.
_NO_EFFORT_FLAG = "error: unknown option '--effort'\n"

AGENT_E = {**AGENT, "effort": "high"}


def test_an_effort_appends_the_flag():
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("do the thing", AGENT_E, model="opus", effort="max")
    assert run.call_args[0][0] == [
        "/usr/local/bin/claude", "-p", "do the thing", "--output-format", "json", "--model", "opus", "--effort", "max",
    ]


def test_a_blank_effort_leaves_argv_unchanged():
    """Regression guard: a run with no effort gets the exact same command as
    before per-video effort existed."""
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("do the thing", AGENT_E, model="opus")
    assert run.call_args[0][0] == ["/usr/local/bin/claude", "-p", "do the thing", "--output-format", "json",
                                   "--model", "opus"]


@pytest.mark.parametrize("bad", ["HIGH", "extreme", "two words", "--flag", "  "])
def test_an_unknown_effort_level_is_dropped_before_the_run(bad):
    """A closed, documented set, so unlike a model this is checkable up front.
    No --effort flag means the CLI's own default: a working run."""
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("prompt", AGENT_E, effort=bad)
    cmd = run.call_args[0][0]
    assert "--effort" not in cmd
    assert run.call_count == 1


@pytest.mark.parametrize("good", ["low", "medium", "high", "xhigh", "max", "  max  "])
def test_every_documented_level_is_passed_through_trimmed(good):
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("prompt", AGENT_E, effort=good)
    cmd = run.call_args[0][0]
    assert cmd[cmd.index("--effort") + 1] == good.strip()


def test_a_cli_without_the_flag_reruns_once_without_it(caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    with patch.object(poll, "_execute",
                      side_effect=[_result(stderr=_NO_EFFORT_FLAG, returncode=1),
                                   _result(stdout="done")]) as run:
        poll.invoke_agent("do the thing", AGENT_E, model="opus", effort="max")
    assert run.call_count == 2
    assert "--effort" in run.call_args_list[0][0][0]
    assert run.call_args_list[1][0][0] == [
        "/usr/local/bin/claude", "-p", "do the thing", "--output-format", "json", "--model", "opus",
    ]
    errors = [r.getMessage() for r in caplog.records if r.levelno == logging.ERROR]
    assert any("does not accept --effort" in m for m in errors)


def test_the_effort_marker_on_stdout_is_ignored():
    """stderr only, deliberately.

    An agent session whose own stdout discusses `unknown option '--effort'` —
    one editing this very file, say — would otherwise strip the flag from every
    run that followed, silently and permanently.
    """
    with patch.object(poll, "_execute",
                      return_value=_result(stdout=_NO_EFFORT_FLAG, returncode=1)) as run:
        poll.invoke_agent("p", AGENT_E, model="opus", effort="max")
    assert run.call_count == 1


def test_an_effort_rejection_with_no_effort_passed_is_not_retried(caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    with patch.object(poll, "_execute",
                      return_value=_result(stderr=_NO_EFFORT_FLAG, returncode=1)) as run:
        poll.invoke_agent("p", AGENT_E, model="opus")
    assert run.call_count == 1
    assert any("nothing to fall back from" in r.getMessage() for r in caplog.records)


def test_a_fallback_still_rejecting_the_flag_is_reported_not_looped(caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    with patch.object(poll, "_execute",
                      return_value=_result(stderr=_NO_EFFORT_FLAG, returncode=1)) as run:
        poll.invoke_agent("p", AGENT_E, model="opus", effort="max")
    assert run.call_count == 2
    assert any("still reports an unknown --effort option" in r.getMessage()
               for r in caplog.records)


def test_both_flags_rejected_drops_effort_first_then_model_and_stops_at_three():
    """The precedence, and the cap.

    Effort goes first because its rejection means the CLI refused to start, so
    nothing else about that run can be believed. Three runs is the ceiling: the
    real one plus one retry per flag. Without a cap this shape loops.
    """
    with patch.object(poll, "_execute", side_effect=[
        _result(stderr=_NO_EFFORT_FLAG, returncode=1),   # 1: --effort unknown
        _result(stdout=_REJECTED),                       # 2: no effort; model rejected
        _result(stdout=_REJECTED),                       # 3: no model either; still rejected
    ]) as run:
        poll.invoke_agent("p", AGENT_E, model="sonnett", effort="max")
    assert run.call_count == 3
    first, second, third = (c[0][0] for c in run.call_args_list)
    assert "--effort" in first and "--model" in first
    assert "--effort" not in second and "--model" in second
    assert "--effort" not in third and "--model" not in third


def test_a_model_rejection_keeps_the_effort_flag():
    """The two flags fail independently — dropping the model must not quietly
    drop a working effort as well."""
    with patch.object(poll, "_execute",
                      side_effect=[_result(stdout=_REJECTED), _result()]) as run:
        poll.invoke_agent("p", AGENT_E, model="sonnett", effort="max")
    assert run.call_count == 2
    retry = run.call_args_list[1][0][0]
    assert retry == ["/usr/local/bin/claude", "-p", "p", "--output-format", "json", "--effort", "max"]


def test_a_dry_run_shows_the_effort_and_runs_nothing(caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    with patch.object(poll, "_execute") as run:
        poll.invoke_agent("secret prompt", AGENT_E, dry_run=True, model="opus", effort="max")
    run.assert_not_called()
    line = next(r.getMessage() for r in caplog.records if "[DRY RUN]" in r.getMessage())
    assert "--effort max" in line
    assert "secret prompt" not in line


def test_the_agent_never_inherits_the_pollers_stdin(tmp_path):
    """`codex exec` reads stdin when it is piped and appends it to the prompt,
    so an inherited stdin can block an unattended tick indefinitely. Claude
    ignores stdin, so this is set unconditionally rather than per-adapter.
    Its own process group is what lets a timeout kill the agent's children."""
    with patch.object(poll.subprocess, "Popen") as popen:
        popen.return_value.pid = 4242
        popen.return_value.wait.return_value = 0
        poll._execute(["true"], cwd=tmp_path)
    assert popen.call_args.kwargs["stdin"] is poll.subprocess.DEVNULL
    assert popen.call_args.kwargs["start_new_session"] is True


def test_a_codex_agent_row_builds_codexs_own_argv(monkeypatch):
    """The poller is agent-agnostic: the row's id selects the adapter, and the
    adapter owns every flag."""
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/local/bin/codex")
    agent = {"id": "codex", "binary": "codex", "run_path": "/tmp/agent-ws",
             "models": ["gpt-5.6-sol"]}
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("do the thing", agent, dry_run=False, model="gpt-5.6-sol",
                          effort="high")
    assert run.call_args.args[0] == [
        "/usr/local/bin/codex", "exec", "--json", "--skip-git-repo-check", "-s", "read-only",
        "-c", 'approvals_reviewer="auto_review"', "-m", "gpt-5.6-sol",
        "-c", "model_reasoning_effort=high", "--", "do the thing"]


def test_codex_never_re_runs_over_the_effort_flag(monkeypatch):
    """Its adapter cannot report an unknown --effort, so a crash that happens
    to mention one must not cost a second billed session."""
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/local/bin/codex")
    agent = {"id": "codex", "binary": "codex", "run_path": "/tmp/agent-ws"}
    result = _result(stderr="error: unknown option '--effort'", returncode=1)
    with patch.object(poll, "_execute", return_value=result) as run:
        poll.invoke_agent("do the thing", agent, dry_run=False, effort="high")
    assert run.call_count == 1


def test_a_fallback_model_that_rejects_the_effort_still_recovers(monkeypatch):
    """The order model-then-effort is reachable and used to be unhandled.

    If the configured model is rejected, the retry keeps the effort and uses
    the CLI's own default model — a model nobody chose, which may not accept
    that effort. The old code read only `model_rejected` from that retry, so
    the tick ended having done nothing, silently, on every cron run.
    """
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/local/bin/codex")
    agent = {"id": "codex", "binary": "codex", "run_path": "/tmp/agent-ws"}
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "-m" in cmd:                       # run 1: the chosen model is rejected
            return _result(stderr="The model `x` does not exist or you do not have access "
                                  "to it.", returncode=1)
        if "model_reasoning_effort=max" in " ".join(cmd):   # run 2: default model, effort kept
            return _result(stderr='"param": "reasoning.effort"', returncode=1)
        return _result()                      # run 3: neither flag

    with patch.object(poll, "_execute", side_effect=fake_run):
        poll.invoke_agent("do the thing", agent, model="bogus", effort="max")

    assert len(calls) == 3, calls
    assert "-m" not in calls[1] and "model_reasoning_effort=max" in " ".join(calls[1])
    assert "-m" not in calls[2] and "model_reasoning_effort" not in " ".join(calls[2])


def test_the_ladder_never_exceeds_three_runs_even_when_everything_is_rejected(monkeypatch):
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/local/bin/codex")
    agent = {"id": "codex", "binary": "codex", "run_path": "/tmp/agent-ws"}
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _result(stderr='"param": "reasoning.effort" and The model `x` does not exist '
                              "or you do not have access to it.", returncode=1)

    with patch.object(poll, "_execute", side_effect=fake_run):
        poll.invoke_agent("do the thing", agent, model="bogus", effort="max")
    assert len(calls) <= 3, calls


# ── OpenCode ────────────────────────────────────────────────────────────────

def _opencode(monkeypatch):
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/local/bin/opencode")
    return {"id": "opencode", "binary": "opencode", "run_path": "/tmp/agent-ws",
            "models": ["anthropic/claude-sonnet-4-5"]}


def test_an_opencode_agent_row_builds_opencodes_own_argv(monkeypatch):
    agent = _opencode(monkeypatch)
    with patch.object(poll, "_execute", return_value=_result()) as run:
        poll.invoke_agent("do the thing", agent, dry_run=False,
                          model="anthropic/claude-sonnet-4-5", effort="high")
    assert run.call_args.args[0] == [
        "/usr/local/bin/opencode", "run", "--auto", "--format", "json",
        "--model", "anthropic/claude-sonnet-4-5#high", "--", "do the thing"]


def test_opencode_retries_without_the_variant_and_keeps_the_model(monkeypatch):
    """OpenCode's two rejections are distinguishable, so an unusable effort
    costs one retry with the chosen model KEPT — unlike an agent where the
    variant failure is indistinguishable from a model failure."""
    agent = _opencode(monkeypatch)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "#max" in " ".join(cmd):
            return _result(stderr="Error: Variant unavailable for m/x: max", returncode=1)
        return _result()

    with patch.object(poll, "_execute", side_effect=fake_run):
        poll.invoke_agent("do the thing", agent, model="m/x", effort="max")
    assert len(calls) == 2, calls
    assert calls[1][-4:] == ["--model", "m/x", "--", "do the thing"]


def test_dropping_opencodes_model_necessarily_drops_the_effort(monkeypatch):
    """The effort IS a suffix on the model, so there is nothing to carry over.
    That is also what makes the ladder's model-then-effort branch unreachable
    here: run 2 sends no effort, so it cannot be rejected for one."""
    agent = _opencode(monkeypatch)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        if "--model" in cmd:
            return _result(stderr="Error: Model unavailable: bogus/bogus", returncode=1)
        return _result()

    with patch.object(poll, "_execute", side_effect=fake_run):
        poll.invoke_agent("do the thing", agent, model="bogus/bogus", effort="max")
    assert len(calls) == 2, calls
    assert "--model" not in calls[1]
    assert "max" not in " ".join(calls[1])


def test_the_opencode_ladder_never_exceeds_three_runs(monkeypatch):
    agent = _opencode(monkeypatch)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(cmd)
        return _result(stderr="Error: Variant unavailable for m/x: max and "
                              "Error: Model unavailable: m/x", returncode=1)

    with patch.object(poll, "_execute", side_effect=fake_run):
        poll.invoke_agent("do the thing", agent, model="m/x", effort="max")
    assert len(calls) <= 3, calls


# ── Usage reporting (TMDEV-107) ──────────────────────────────────────────────

import json  # noqa: E402

_CLAUDE_OUT = json.dumps({"total_cost_usd": 0.12, "modelUsage": {"claude-opus-5-5": {
    "inputTokens": 100, "outputTokens": 20, "costUSD": 0.12,
    "canonicalModel": "claude-opus-5-5"}}})


class _Posted:
    """urlopen stand-in that answers like the route: {"recorded": n, "events": n}."""

    def __init__(self, recorded=None):
        self.bodies = []
        self._recorded = recorded

    def __call__(self, req, timeout=None):
        body = json.loads(req.data.decode())
        self.bodies.append((req.full_url, body))
        n = len(body["events"]) if self._recorded is None else self._recorded
        self._reply = json.dumps({"recorded": n, "events": len(body["events"])}).encode()
        return self

    def read(self):
        return self._reply

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_each_run_posts_its_usage_with_the_batch_attribution(monkeypatch):
    posted = _Posted()
    monkeypatch.setattr("urllib.request.urlopen", posted)
    with patch.object(poll, "_execute", return_value=_result(stdout=_CLAUDE_OUT)):
        poll.invoke_agent("p", AGENT, model="opus", operation="agent_pipeline",
                          attribution=[{"video_id": "v1", "stage": "TOPIC_APPROVED"}])
    [(url, body)] = posted.bodies
    assert url.endswith("/usage/agent-session")
    assert body["operation"] == "agent_pipeline" and body["agent"] == "claude"
    assert body["videos"] == [{"video_id": "v1", "stage": "TOPIC_APPROVED"}]
    assert body["events"][0]["reported_cost_usd"] == pytest.approx(0.12)


def test_a_retry_is_a_second_billed_session_and_is_posted_too(monkeypatch):
    posted = _Posted()
    monkeypatch.setattr("urllib.request.urlopen", posted)
    rejected = _result(stdout="", stderr="[claude-code:unrecognized_model]", returncode=1)
    with patch.object(poll, "_execute",
                      side_effect=[rejected, _result(stdout=_CLAUDE_OUT)]):
        poll.invoke_agent("p", AGENT, model="sonnett")
    # The rejected run reported no usage (it never started); the retry did.
    assert len(posted.bodies) == 1


def test_a_failed_usage_post_is_harmless_and_logs_the_payload(monkeypatch, caplog):
    def refuse(req, timeout=None):
        raise OSError("connection refused")
    monkeypatch.setattr("urllib.request.urlopen", refuse)
    with patch.object(poll, "_execute", return_value=_result(stdout=_CLAUDE_OUT)) as run:
        poll.invoke_agent("p", AGENT, model="opus")
    assert run.call_count == 1  # the run itself is not retried over bookkeeping
    assert "Could not record this run's usage" in caplog.text
    assert '"reported_cost_usd": 0.12' in caplog.text  # units recoverable from the log


def test_a_dry_run_reports_no_usage(monkeypatch):
    posted = _Posted()
    monkeypatch.setattr("urllib.request.urlopen", posted)
    with patch.object(poll, "_execute") as run:
        poll.invoke_agent("p", AGENT, dry_run=True)
    run.assert_not_called()
    assert posted.bodies == []


def test_a_partly_recorded_report_is_treated_as_a_failure(monkeypatch, caplog):
    """The route answers 200 even when some events failed to record; the lost
    units must still land in the log, not be reported as a success."""
    monkeypatch.setattr("urllib.request.urlopen", _Posted(recorded=0))
    with patch.object(poll, "_execute", return_value=_result(stdout=_CLAUDE_OUT)):
        poll.invoke_agent("p", AGENT, model="opus")
    assert "only 0 of 1 event(s) were recorded" in caplog.text
    assert '"reported_cost_usd": 0.12' in caplog.text
    assert "Recorded usage" not in caplog.text


def test_an_opencode_usage_read_is_retried_and_its_failure_logged(monkeypatch, caplog):
    """Seen live: the session read failed right after a run that ended on a
    provider error, then worked moments later. A silent miss drops to the
    stream fallback, which can lose the last step."""
    posted = _Posted()
    monkeypatch.setattr("urllib.request.urlopen", posted)
    monkeypatch.setattr(poll.time, "sleep", lambda s: None)
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/bin/opencode")
    stream = '{"type":"text","sessionID":"ses_1","part":{"text":"done"}}'
    page = json.dumps({"data": [{"type": "assistant", "cost": 0.5,
                                 "model": {"id": "claude-sonnet-5", "providerID": "openrouter"},
                                 "tokens": {"input": 10, "output": 2}}]})
    reads = [_result(stdout="", stderr="service busy", returncode=1),  # first read fails
             _result(stdout=page)]                                    # second read works
    agent = {**AGENT, "id": "opencode", "binary": "opencode"}
    with patch.object(poll, "_execute", return_value=_result(stdout=stream)), \
         patch.object(poll.subprocess, "run", side_effect=reads):
        poll.invoke_agent("p", agent, model="openrouter/anthropic/claude-sonnet-5")
    assert "attempt 1 of 3" in caplog.text and "service busy" in caplog.text
    [(_, body)] = posted.bodies
    assert body["events"][0]["estimated"] is False
    assert body["events"][0]["reported_cost_usd"] == pytest.approx(0.5)


# ── What a run leaves in the logs (TMDEV-124) ────────────────────────────────
# JSON output modes make stdout the whole session, so the log gets the
# adapter's summary. Trimming is log-only: the verdicts still read everything.

from agent_adapters import LOG_OUTPUT_CAP  # noqa: E402

_CODEX = {"id": "codex", "binary": "codex", "run_path": "/tmp/agent-ws"}


def test_the_log_gets_the_summary_not_the_session(monkeypatch, caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    monkeypatch.setattr(poll, "resolve_agent_binary", lambda agent: "/usr/local/bin/codex")
    stream = "\n".join([
        json.dumps({"type": "item.completed", "item": {
            "id": "1", "type": "mcp_tool_call", "tool": "list_videos", "status": "completed",
            "result": {"content": [{"type": "text", "text": "TOOL-RESULT-" + "x" * 50_000}]}}}),
        json.dumps({"type": "item.completed", "item": {
            "id": "2", "type": "agent_message", "text": "Scripted vid_1."}}),
    ])
    with patch.object(poll, "_execute", return_value=_result(stdout=stream)):
        poll.invoke_agent("p", _CODEX)
    assert "Agent result — 1 tool call: list_videos\nScripted vid_1." in caplog.text
    assert "TOOL-RESULT-" not in caplog.text


def test_a_long_stderr_is_logged_by_its_tail(caplog):
    caplog.set_level(logging.INFO, logger=poll.log.name)
    stderr = "EARLY-NOISE " + "n" * (LOG_OUTPUT_CAP * 2) + " FINAL-ERROR"
    with patch.object(poll, "_execute", return_value=_result(stderr=stderr)):
        poll.invoke_agent("p", AGENT)
    [warning] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Agent stderr")]
    assert warning.endswith("FINAL-ERROR") and "EARLY-NOISE" not in warning
    assert len(warning) < LOG_OUTPUT_CAP + 200


def test_a_rejection_past_the_log_cap_is_still_caught():
    """The summary is for reading only — the verdict reads the whole output."""
    stdout = "z" * (LOG_OUTPUT_CAP * 3) + "\n" + _REJECTED
    with patch.object(poll, "_execute",
                      side_effect=[_result(stdout=stdout), _result()]) as run:
        poll.invoke_agent("p", AGENT, model="sonnett")
    assert run.call_count == 2
