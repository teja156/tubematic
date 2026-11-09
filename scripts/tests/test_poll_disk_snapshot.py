"""poll.py's disk-usage snapshot (TMDEV-192).

The supervisor re-measures the host half of the dashboard's disk figure
(images, container layers, the install folder) at most hourly. What matters:
it runs before the pass, so a paused pipeline, a down API or a missing agent
still gets a fresh figure; the measurement runs detached, so a slow Docker
never holds up a tick; a dry run never measures; and a failure never costs a
tick, nor turns into a new attempt on every pass.
"""
import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

import poll

# conftest replaces the function with a no-op for every other poll test.
_REAL = poll._refresh_disk_snapshot


@pytest.fixture
def spawn(tmp_path, monkeypatch):
    started = []
    class FakePopen:
        def __init__(self, argv, **kw):
            started.append((argv, kw))
    monkeypatch.setattr(poll, "DATA_ROOT", tmp_path / "data-root")
    monkeypatch.setattr(poll, "DISK_SNAPSHOT_LOG", tmp_path / "logs" / "disk-usage.log")
    monkeypatch.setattr(poll.subprocess, "Popen", FakePopen)
    monkeypatch.setattr(poll, "_disk_snapshot_retry_at", 0.0)
    return started


def test_a_missing_snapshot_starts_a_detached_measurement_of_this_install(spawn, tmp_path):
    _REAL()
    assert len(spawn) == 1
    argv, kw = spawn[0]
    assert argv[1:4] == ["-m", "tubematic_core.disk_usage", "--data-root"]
    assert argv[4] == str(tmp_path / "data-root")
    assert argv[argv.index("--install-dir") + 1] == str(poll.SCRIPTS_DIR.parent)
    assert argv[argv.index("--max-age") + 1] == "3600"
    # detached: it outlives the supervisor and never holds up a tick
    assert kw["start_new_session"] is True
    assert kw["cwd"] == poll.SCRIPTS_DIR.parent


def test_a_fresh_snapshot_starts_nothing(spawn, tmp_path):
    path = tmp_path / "data-root" / "data" / "disk-usage.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    _REAL()
    assert spawn == []


def test_it_starts_at_most_once_an_hour_per_supervisor(spawn):
    _REAL()
    _REAL()
    _REAL()
    assert len(spawn) == 1


def test_a_stale_snapshot_starts_a_measurement(spawn, tmp_path):
    path = tmp_path / "data-root" / "data" / "disk-usage.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    old = path.stat().st_mtime - 7200
    os.utime(path, (old, old))
    _REAL()
    assert len(spawn) == 1


def test_a_failed_start_is_logged_and_swallowed(tmp_path, monkeypatch, caplog):
    monkeypatch.setattr(poll, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(poll, "DISK_SNAPSHOT_LOG", tmp_path / "disk-usage.log")
    monkeypatch.setattr(poll, "_disk_snapshot_retry_at", 0.0)
    def boom(*a, **kw):
        raise OSError("no python")
    monkeypatch.setattr(poll.subprocess, "Popen", boom)
    with caplog.at_level(logging.WARNING, logger="poll"):
        _REAL()
        _REAL()
    assert sum("disk-usage measurement" in r.getMessage() for r in caplog.records) == 1


def _supervise(monkeypatch, *, dry_run, status):
    seen = []
    monkeypatch.setattr(poll, "_refresh_disk_snapshot", lambda: seen.append("snapshot"))
    def fetch_status():
        seen.append("pass")
        return status
    monkeypatch.setattr(poll, "_fetch_pipeline_status", fetch_status)
    monkeypatch.setattr(poll, "_fetch_agents", lambda: [])
    poll._Supervisor(dry_run).run()
    return seen


def test_it_runs_before_the_pass_even_when_the_api_is_down(monkeypatch):
    assert _supervise(monkeypatch, dry_run=False, status={}) == ["snapshot", "pass"]


def test_it_runs_while_the_pipeline_is_paused(monkeypatch):
    seen = _supervise(monkeypatch, dry_run=False, status={"paused": True})
    assert seen[0] == "snapshot"


def test_a_dry_run_never_measures(monkeypatch):
    assert "snapshot" not in _supervise(monkeypatch, dry_run=True, status={})
