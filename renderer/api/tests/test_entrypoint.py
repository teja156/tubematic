"""renderer/entrypoint.sh's permission preamble, run for real (TMDEV-94).

The shared logs directory has a writer that is not a container: scripts/poll.py
runs from cron as the host user and appends poll.<date>.jsonl there. The
entrypoint used to fix up only the DB directory, so a root-owned logs/ was never
repaired and every poll entry silently dropped off the dashboard.

A non-root test user cannot create a root-owned directory, so only the normal
branch (host-owned data directory) is exercised: that the logs directory ends up
in the data directory's group, group-writable, with setgid so the files the
containers create there stay in that group too.
"""
import os
import stat
import subprocess
from pathlib import Path

import pytest

ENTRYPOINT = Path(__file__).resolve().parents[2] / "entrypoint.sh"

pytestmark = pytest.mark.skipif(
    os.geteuid() == 0, reason="root takes the chgrp/chmod paths for granted")


def _run(tmp_path, log_dir):
    data = tmp_path / "data"
    data.mkdir(exist_ok=True)
    env = {**os.environ,
           "TUBEMATIC_DB": str(data / "tubematic.db"),
           "TUBEMATIC_LOG_DIR": str(log_dir)}
    return subprocess.run(["sh", str(ENTRYPOINT), "true"], env=env,
                          capture_output=True, text=True, timeout=30)


@pytest.mark.parametrize("before", [0o755, 0o700])
def test_logs_dir_is_made_group_usable_with_setgid(tmp_path, before):
    """0755 is the shape reported (no group write). 0700 is the one that makes
    write alone useless: without search (x) the group cannot create a file in
    the directory at all, and without read poll.py cannot list it to prune."""
    logs = tmp_path / "logs"
    logs.mkdir()
    logs.chmod(before)

    result = _run(tmp_path, logs)

    assert result.returncode == 0, result.stderr
    mode = logs.stat().st_mode
    for bit in (stat.S_IRGRP, stat.S_IWGRP, stat.S_IXGRP, stat.S_ISGID):
        assert mode & bit, oct(mode)
    assert logs.stat().st_gid == (tmp_path / "data").stat().st_gid


def test_a_missing_logs_dir_does_not_fail_the_container(tmp_path):
    """Every step is failure-tolerant: the e2e stack mounts no /logs at all,
    and a permission preamble must never stop the service it precedes."""
    result = _run(tmp_path, tmp_path / "no-such-logs")
    assert result.returncode == 0, result.stderr
