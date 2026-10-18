"""poll.py's structured JSONL sink (TMDEV-86).

poll.py is the one writer that runs on the host rather than in a container, and
the one with a documented "no database access" invariant. Both shape these
tests: retention has to arrive over HTTP, and poll.log must be left alone.
"""
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

import poll
from tubematic_core.logging import log_filename


@pytest.fixture(autouse=True)
def _restore_root_handlers():
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    for h in before:
        if h not in root.handlers:
            root.addHandler(h)
    root.setLevel(level)


def test_poll_py_still_has_no_database_access(monkeypatch):
    """A documented invariant (scripts/config.py, pipeline.get_pipeline_status).
    The ticket's own sketch had this module reading the settings table directly,
    which would have spent that invariant to fetch one integer."""
    source = Path(poll.__file__).read_text()
    code = "\n".join(
        line for line in source.splitlines() if not line.lstrip().startswith("#")
    )
    for forbidden in ("import sqlite3", "import db", "TUBEMATIC_DB"):
        assert forbidden not in code, forbidden


def test_retention_comes_over_http(monkeypatch):
    monkeypatch.setattr(poll, "RENDERER_URL", "http://api.invalid")
    payload = json.dumps({"log_retention_days": 30}).encode()

    class _Resp:
        def read(self):
            return payload

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    assert poll._json_log_retention_days() == 30


def test_an_unreachable_api_falls_back_to_the_default(monkeypatch):
    """Which is also what a fresh install gets, before anything is seeded."""
    def boom(*a, **k):
        raise OSError("connection refused")

    monkeypatch.setattr("urllib.request.urlopen", boom)
    assert poll._json_log_retention_days() == poll.LOG_RETENTION_DAYS


@pytest.mark.parametrize("value", [0, -5, 366, "nonsense", None])
def test_an_out_of_range_or_junk_value_falls_back(monkeypatch, value):
    class _Resp:
        def read(self):
            return json.dumps({"log_retention_days": value}).encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *a, **k: _Resp())
    assert poll._json_log_retention_days() == poll.LOG_RETENTION_DAYS


def test_setup_writes_jsonl_alongside_poll_log_without_replacing_it(tmp_path, monkeypatch):
    """poll.log is a different store and is named in existing cron-tick checks.
    The JSONL sink is added beside it, never instead of it."""
    monkeypatch.setattr(poll, "LOG_DIR", tmp_path / "agent-logs")
    monkeypatch.setattr(poll, "JSONL_LOG_DIR", tmp_path / "shared-logs")
    (tmp_path / "shared-logs").mkdir()
    monkeypatch.setattr(poll, "_json_log_retention_days", lambda: 14)

    poll._setup_logging()
    poll.log.info("tick")

    assert (tmp_path / "agent-logs" / "poll.log").exists()

    from datetime import datetime, timezone
    jsonl = tmp_path / "shared-logs" / log_filename(
        "poll", datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    assert jsonl.exists()
    record = json.loads(jsonl.read_text().splitlines()[-1])
    assert record["service"] == "poll"
    assert record["message"] == "tick"


@pytest.mark.skipif(os.geteuid() == 0,
                    reason="root bypasses the directory permissions under test")
def test_an_unwritable_shared_directory_leaves_poll_log_working(tmp_path, monkeypatch):
    """The shared directory is a bind mount dockerd can leave root-owned. That
    must degrade, not take the poller's own logging down with it."""
    import stat

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(stat.S_IRUSR | stat.S_IXUSR)  # cannot create anything inside
    monkeypatch.setattr(poll, "LOG_DIR", tmp_path / "agent-logs")
    monkeypatch.setattr(poll, "JSONL_LOG_DIR", blocked / "logs")
    monkeypatch.setattr(poll, "_json_log_retention_days", lambda: 14)

    try:
        poll._setup_logging()
        poll.log.info("tick")
        assert (tmp_path / "agent-logs" / "poll.log").exists()
        assert not (blocked / "logs").exists()
    finally:
        blocked.chmod(stat.S_IRWXU)


@pytest.mark.skipif(os.geteuid() == 0,
                    reason="root bypasses the directory permissions under test")
def test_an_unwritable_shared_directory_is_reported_in_poll_log(tmp_path, monkeypatch):
    """setup_json_logging returns None quietly by design; poll.py must not.
    On a release install a root-owned logs/ dropped every poll entry from the
    dashboard with nothing in poll.log, the terminal or the Logs page to say so.
    The warning has to name the directory, or it cannot be acted on."""
    import stat

    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(stat.S_IRUSR | stat.S_IXUSR)
    monkeypatch.setattr(poll, "LOG_DIR", tmp_path / "agent-logs")
    monkeypatch.setattr(poll, "JSONL_LOG_DIR", blocked / "logs")
    monkeypatch.setattr(poll, "_json_log_retention_days", lambda: 14)

    try:
        poll._setup_logging()
        text = (tmp_path / "agent-logs" / "poll.log").read_text()
        assert "WARNING" in text
        assert str(blocked / "logs") in text
        assert "chown" in text
    finally:
        blocked.chmod(stat.S_IRWXU)


def test_a_writable_shared_directory_logs_no_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(poll, "LOG_DIR", tmp_path / "agent-logs")
    monkeypatch.setattr(poll, "JSONL_LOG_DIR", tmp_path / "shared-logs")
    monkeypatch.setattr(poll, "_json_log_retention_days", lambda: 14)

    poll._setup_logging()
    assert "WARNING" not in (tmp_path / "agent-logs" / "poll.log").read_text()
