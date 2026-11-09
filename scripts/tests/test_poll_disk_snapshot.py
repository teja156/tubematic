"""poll.py's disk-usage snapshot (TMDEV-192).

The supervisor re-measures the host half of the dashboard's disk figure
(images, container layers, the install folder) at most hourly. What matters:
it runs before the pass, so a paused pipeline, a down API or a missing agent
still gets a fresh figure; a dry run never touches Docker; and a failure never
costs a tick, nor turns into a re-measure on every pass.
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
def snap(tmp_path, monkeypatch):
    calls = []
    def refresh(data_root, install_dir, *, max_age=None):
        calls.append((data_root, install_dir, max_age))
        return True
    monkeypatch.setattr(poll, "DATA_ROOT", tmp_path / "data-root")
    monkeypatch.setattr(poll.disk_usage, "refresh_snapshot", refresh)
    monkeypatch.setattr(poll, "_disk_snapshot_retry_at", 0.0)
    return calls


def test_it_asks_for_an_hourly_refresh_of_this_install(snap, tmp_path):
    _REAL()
    assert snap == [(tmp_path / "data-root", poll.SCRIPTS_DIR.parent, 3600)]


def test_a_failure_is_logged_once_and_not_retried_every_pass(tmp_path, monkeypatch, caplog):
    calls = []
    def refresh(*a, **kw):
        calls.append(a)
        raise PermissionError("data/ is root-owned")
    monkeypatch.setattr(poll, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(poll.disk_usage, "refresh_snapshot", refresh)
    monkeypatch.setattr(poll, "_disk_snapshot_retry_at", 0.0)
    with caplog.at_level(logging.WARNING, logger="poll"):
        _REAL()
        _REAL()
        _REAL()
    assert len(calls) == 1
    assert sum("disk-usage snapshot" in r.getMessage() for r in caplog.records) == 1


def test_any_exception_is_swallowed(tmp_path, monkeypatch):
    monkeypatch.setattr(poll, "DATA_ROOT", tmp_path)
    monkeypatch.setattr(poll.disk_usage, "refresh_snapshot",
                        lambda *a, **kw: (_ for _ in ()).throw(ValueError("odd docker output")))
    monkeypatch.setattr(poll, "_disk_snapshot_retry_at", 0.0)
    _REAL()  # no raise


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
