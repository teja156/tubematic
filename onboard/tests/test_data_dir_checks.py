"""check_prerequisites' write probe on ~/.tubematic-data's subdirectories (TMDEV-94).

poll.py writes its JSONL trail into logs/ from cron as the host user. A
root-owned logs/ used to drop every poll entry from the dashboard with nothing
reporting it, so onboarding now surfaces an unwritable subdirectory up front.

The names are patched on onboard.checks, where check_prerequisites looks them
up -- patching onboard.config would leave the imported aliases untouched and
the test would silently probe the real home directory.
"""
import os
import stat
import subprocess

import pytest

from onboard import checks


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    root = tmp_path / ".tubematic-data"
    for d in ("logs", "jobs"):
        (root / d).mkdir(parents=True)
    monkeypatch.setattr(checks, "DATA_ROOT", root)
    monkeypatch.setattr(checks, "DATA_SUBDIRS", ("logs", "jobs", "backups"))
    monkeypatch.setattr(checks, "DB_PATH", root / "data" / "tubematic.db")
    # Keep the Docker/Node probes off the real machine.
    monkeypatch.setattr(checks, "_run", lambda cmd: subprocess.CompletedProcess(cmd, 0, "v22.0.0", ""))
    yield root
    for d in root.iterdir():
        d.chmod(stat.S_IRWXU)


def _writable_items(items):
    return [i for i in items if "writable by current user" in i.label]


def test_writable_subdirectories_produce_no_item(data_root):
    assert _writable_items(checks.check_prerequisites()) == []


@pytest.mark.skipif(os.geteuid() == 0,
                    reason="root bypasses the directory permissions under test")
def test_an_unwritable_subdirectory_is_a_warning_naming_the_fix(data_root):
    logs = data_root / "logs"
    logs.chmod(stat.S_IRUSR | stat.S_IXUSR)

    [item] = _writable_items(checks.check_prerequisites())

    assert str(logs) in item.label
    assert item.ok is False
    # A warning, never an error: the containers run as root and still work,
    # so this must not block onboarding.
    assert item.severity == "warning"
    assert "sudo chown" in item.hint and str(logs) in item.hint


@pytest.mark.skipif(os.geteuid() == 0,
                    reason="root bypasses the directory permissions under test")
def test_write_without_search_permission_is_still_a_warning(data_root):
    """Write alone cannot create a child: the directory also needs search (x).
    A W_OK-only probe passed this shape while poll.py still could not create
    its log file there."""
    logs = data_root / "logs"
    logs.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0600: writable, not searchable

    [item] = _writable_items(checks.check_prerequisites())
    assert str(logs) in item.label


def test_a_missing_subdirectory_is_not_judged(data_root):
    """backups/ does not exist yet; the directories step creates it as this
    user, which is the right owner, so there is nothing to warn about."""
    assert not (data_root / "backups").exists()
    assert _writable_items(checks.check_prerequisites()) == []


def test_the_probe_covers_every_directory_onboarding_creates():
    """One list drives both the directories step and this probe."""
    from onboard.config import DATA_SUBDIRS
    assert checks.DATA_SUBDIRS is DATA_SUBDIRS
    assert "logs" in DATA_SUBDIRS
