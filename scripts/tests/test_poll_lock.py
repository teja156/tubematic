"""Where the poll lock lives, and that a run never deletes it."""
import pytest

import poll


def test_the_lock_sits_beside_the_logs_not_in_tmp():
    """A known location — and one pollers sharing a home directory share."""
    assert poll.LOCKFILE == poll.LOG_DIR.parent / "poll.lock"
    assert not str(poll.LOCKFILE).startswith("/tmp")


def test_a_finished_run_leaves_the_lock_file_in_place(tmp_path, monkeypatch):
    """Unlinking a flock'd file lets two pollers each hold a lock on a
    different inode, so the file must outlive every run."""
    lock = tmp_path / "agent" / "poll.lock"
    monkeypatch.setattr(poll, "LOCKFILE", lock)
    monkeypatch.setattr(poll, "_setup_logging", lambda dry_run=False: None)
    monkeypatch.setattr(poll, "_fetch_pipeline_status", lambda: {})
    monkeypatch.setattr(poll.sys, "argv", ["poll.py"])
    with pytest.raises(SystemExit):
        poll.main()
    assert lock.exists()
