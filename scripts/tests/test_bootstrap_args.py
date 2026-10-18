"""poll.py's cron-line contract (TMDEV-90).

The cron line names no agent any more: which agent runs, from which binary and
workspace, is resolved per video over HTTP. poll.py's own log directory is the
one thing that cannot come from the API — logging starts before the first HTTP
call — so it is a fixed path. A crontab written before this change still passes
--agent-run-path/--agent-binary; those are ignored with a warning rather than
failing, so an upgrade that has not re-run the cron step keeps running.
"""
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

import config
import poll


def test_log_dir_is_the_fixed_poll_log_dir():
    assert poll.LOG_DIR == config.POLL_LOG_DIR
    assert poll.LOG_DIR == Path("~/.tubematic-agent/logs").expanduser()


@pytest.mark.parametrize("argv,expected", [
    (["poll.py"], []),
    (["poll.py", "--dry-run"], []),
    (["poll.py", "--agent-run-path", "/srv/agent"], ["--agent-run-path"]),
    (["poll.py", "--agent-run-path", "/srv/a", "--agent-binary", "/usr/bin/claude"],
     ["--agent-run-path", "--agent-binary"]),
    (["poll.py", "--agent-binary"], ["--agent-binary"]),
])
def test_legacy_flags_are_detected(argv, expected):
    assert poll._legacy_flags(argv) == expected


def test_a_legacy_crontab_warns_and_still_runs(tmp_path, monkeypatch, caplog):
    """The old flags must not change behaviour — only produce a warning."""
    monkeypatch.setattr(poll, "_setup_logging", lambda dry_run=False: None)
    monkeypatch.setattr(poll, "LOCKFILE", tmp_path / "poll.lock")
    monkeypatch.setattr(sys, "argv",
                        ["poll.py", "--agent-run-path", "/srv/a", "--agent-binary", "/bin/x"])
    with patch("poll._fetch_pipeline_status", return_value={}):
        with pytest.raises(SystemExit):
            poll.main()
    assert "Ignoring --agent-run-path, --agent-binary" in caplog.text
    assert "--step cron" in caplog.text


def test_prompts_point_at_the_absolute_poll_log():
    """The agent's cwd is its own workspace, which for a second agent is not
    the poll log directory — a relative ./logs/poll.log would point nowhere."""
    for prompt in (poll.build_pipeline_prompt("vid_a", "VOICE_READY"),
                   poll.build_script_profile_prompt("prof-1"),):
        assert str(poll.LOG_DIR / "poll.log") in prompt
        assert "./logs/poll.log" not in prompt


# ── One video per session (TMDEV-73, TMDEV-129) ─────────────────────────────

def test_prompt_names_the_one_video_to_work_on():
    """The agent must not wander onto videos another session is working."""
    prompt = poll.build_pipeline_prompt("vid_a", "VOICE_READY")
    assert "scoped to video vid_a" in prompt
    assert "Work only on this video" in prompt
