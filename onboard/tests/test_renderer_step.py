"""The `renderer` step starts and health-checks three containers (TMDEV-87).

Flask and MCP used to be one container, so onboarding started two services and
waited on one healthcheck. Since the split there are three services and two
independent healthchecks — and a healthy Flask no longer implies the agent's
tools are reachable, which is the whole reason the wait was duplicated rather
than kept as one probe.
"""
import subprocess

import pytest

import onboard.actions as actions
from onboard.executor import Executor, NullReporter


class _Rep(NullReporter):
    def __init__(self):
        self.oks, self.warns, self.fails, self.infos = [], [], [], []
    def ok(self, msg, *a, **k): self.oks.append(msg)
    def warn(self, msg, *a, **k): self.warns.append(msg)
    def fail(self, msg, *a, **k): self.fails.append(msg)
    def info(self, msg, *a, **k): self.infos.append(msg)


def _health(statuses: dict):
    """Stub `docker inspect`, returning a state string per container name."""
    def run(cmd, **kw):
        name = cmd[-1]
        return subprocess.CompletedProcess(cmd, 0, statuses.get(name, "") + "\n", "")
    return run


@pytest.fixture
def no_volume_reconcile(monkeypatch):
    monkeypatch.setattr(actions, "_reconcile_volume_devices", lambda ex, rep: None)


@pytest.fixture
def instant(monkeypatch):
    """The wait loop sleeps 5s between polls; nothing here should take 60s."""
    monkeypatch.setattr(actions.time, "sleep", lambda s: None)


# ── What gets started ──────────────────────────────────────────────────────

def test_all_three_containers_are_started(no_volume_reconcile, monkeypatch):
    ex = Executor(dry_run=True)
    actions.apply_renderer(None, ex, _Rep())
    ups = [i.detail for i in ex.intents if "up" in i.detail]
    assert any(
        "tubematic-api" in i and "tubematic-mcp" in i and "tubematic-renderer" in i
        for i in ups
    ), ups


def test_only_one_image_is_built(no_volume_reconcile):
    """One image serves all three services — building tubematic-api covers
    tubematic-mcp and tubematic-renderer too."""
    ex = Executor(dry_run=True)
    actions.apply_renderer(None, ex, _Rep())
    builds = [i.detail for i in ex.intents if "build" in i.detail]
    assert len(builds) == 1
    assert "tubematic-api" in builds[0]
    assert "tubematic-mcp" not in builds[0]


def test_dry_run_stops_before_waiting(no_volume_reconcile):
    rep = _Rep()
    actions.apply_renderer(None, Executor(dry_run=True), rep)
    assert rep.oks == ["Image built"]


# ── Waiting on both healthchecks ───────────────────────────────────────────

def test_both_containers_are_reported_when_healthy(monkeypatch, instant):
    monkeypatch.setattr(actions.subprocess, "run", _health({
        "tubematic-api": "healthy",
        "tubematic-mcp": "healthy",
        "tubematic-renderer": "running",
    }))
    rep = _Rep()
    assert actions._await_health("tubematic-api", "http://localhost:4000", rep) is True
    assert actions._await_health("tubematic-mcp", "http://localhost:4100/mcp", rep) is True
    assert any("tubematic-api" in m for m in rep.oks)
    assert any("tubematic-mcp" in m for m in rep.oks)


def test_an_unhealthy_container_fails_and_names_itself(monkeypatch, instant):
    """The hint must name the container that is actually broken — pointing at
    tubematic-api for an MCP failure is what made the combined check useless."""
    monkeypatch.setattr(actions.subprocess, "run", _health({"tubematic-mcp": "unhealthy"}))
    rep = _Rep()
    assert actions._await_health("tubematic-mcp", "http://localhost:4100/mcp", rep) is False
    assert any("tubematic-mcp" in m for m in rep.fails)
    assert rep.oks == []


def test_a_timeout_warns_rather_than_failing(monkeypatch, instant):
    """A container still in `starting` may yet come up; onboarding says so
    instead of declaring the install broken."""
    monkeypatch.setattr(actions.subprocess, "run", _health({"tubematic-api": "starting"}))
    rep = _Rep()
    assert actions._await_health("tubematic-api", "http://localhost:4000", rep) is False
    assert rep.warns and rep.fails == []


def test_a_sick_api_stops_before_the_mcp_wait(monkeypatch, instant, no_volume_reconcile):
    """apply_renderer returns on the first failure, so a broken API does not
    then spend 60s waiting on an MCP container that was gated behind it."""
    monkeypatch.setattr(actions.subprocess, "run", _health({"tubematic-api": "unhealthy"}))
    rep = _Rep()
    ex = Executor(dry_run=False)
    monkeypatch.setattr(ex, "run", lambda *a, **k: subprocess.CompletedProcess([], 0, "", ""))
    actions.apply_renderer(None, ex, rep)
    assert any("tubematic-api" in m for m in rep.fails)
    assert not any("tubematic-mcp" in m for m in rep.fails + rep.oks)
