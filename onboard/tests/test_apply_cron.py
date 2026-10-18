"""apply_cron (TMDEV-44): a single poll.py cron line, no separate research
entry. subprocess.run for the read-only `crontab -l` is monkeypatched so this
test is hermetic regardless of the host's actual crontab contents."""
import subprocess
from unittest.mock import patch

from onboard.actions import apply_cron
from onboard.config import OnboardConfig
from onboard.executor import Executor, NullReporter


def _run_apply_cron(existing_crontab: str = "", **overrides):
    values = {"POLL_INTERVAL_MINS": "30"}
    values.update(overrides)
    cfg = OnboardConfig(values=values)
    ex = Executor(dry_run=True)
    with patch(
        "onboard.actions.subprocess.run",
        return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout=existing_crontab),
    ):
        apply_cron(cfg, ex, NullReporter())
    write_intents = [i for i in ex.intents if i.kind == "crontab_write"]
    assert len(write_intents) == 1
    return write_intents[0].detail


def test_apply_cron_emits_exactly_one_poll_py_line():
    written = _run_apply_cron()
    # Executor's dry-run intent joins the crontab content's lines with a
    # literal " \n " marker (see Executor.crontab_write) instead of real
    # newlines, so split on that rather than str.splitlines().
    lines = written.split(" \\n ")
    poll_lines = [l for l in lines if "poll.py" in l]
    assert len(poll_lines) == 1
    assert "--research" not in poll_lines[0]
    assert poll_lines[0].strip().startswith("*/30 * * * *")


def test_apply_cron_removes_a_previously_written_research_line():
    stale = (
        "# Tubematic — managed by onboard.py — do not edit manually\n"
        "*/30 * * * * /usr/bin/python3 /repo/scripts/poll.py >> /log 2>&1\n"
        "0 9 * * * /usr/bin/python3 /repo/scripts/poll.py --research >> /log 2>&1\n"
    )
    written = _run_apply_cron(existing_crontab=stale)
    lines = written.split(" \\n ")
    poll_lines = [l for l in lines if "poll.py" in l]
    assert len(poll_lines) == 1
    assert "--research" not in written


# ── The line names no agent (TMDEV-90) ──────────────────────────────────────
# poll.py resolves the agent — binary, workspace, model — per video over HTTP,
# so installing or re-installing an agent never touches cron. The one thing it
# cannot get over HTTP is where to log, so that is a fixed directory.

def _poll_line(written: str) -> str:
    return next(l for l in written.split(" \\n ") if "poll.py" in l)


def test_the_line_names_no_agent():
    line = _poll_line(_run_apply_cron())
    assert "--agent-run-path" not in line
    assert "--agent-binary" not in line
    assert "claude" not in line


def test_cron_output_goes_to_the_fixed_poll_log_dir():
    from onboard.config import POLL_LOG_DIR
    assert f">> {POLL_LOG_DIR / 'cron.log'} 2>&1" in _poll_line(_run_apply_cron())


def test_the_log_dir_is_created_before_the_line_is_written():
    """The shell redirect fails — and the tick with it — if the directory is
    missing, and on a fresh install nothing else has created it yet."""
    from onboard.config import POLL_LOG_DIR
    ex = Executor(dry_run=True)
    with patch("onboard.actions.subprocess.run",
               return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="")):
        apply_cron(OnboardConfig(values={"POLL_INTERVAL_MINS": "30"}), ex, NullReporter())
    kinds = [(i.kind, i.detail) for i in ex.intents]
    mkdir = kinds.index(("mkdir", str(POLL_LOG_DIR)))
    write = next(n for n, (kind, _) in enumerate(kinds) if kind == "crontab_write")
    assert mkdir < write


def test_apply_cron_honours_the_chosen_interval():
    assert _poll_line(_run_apply_cron(POLL_INTERVAL_MINS="15")).strip().startswith("*/15 * * * *")


def test_apply_cron_records_the_interval_for_the_next_prefill(tmp_path, monkeypatch):
    """It was prompted but never persisted before — absent from write_env_vars'
    key list — so the question always re-defaulted to 30 whatever the user had
    chosen. Dry-run records the intent rather than writing."""
    import sqlite3
    db = tmp_path / "tubematic.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    monkeypatch.setattr("onboard.actions.DB_PATH", db)

    cfg = OnboardConfig(values={"POLL_INTERVAL_MINS": "45"})
    ex = Executor(dry_run=False)
    monkeypatch.setattr(ex, "mkdir", lambda *a, **k: None)  # never the real ~ path
    with patch("onboard.actions.subprocess.run",
                return_value=subprocess.CompletedProcess(args=[], returncode=0, stdout="")), \
         patch.object(ex, "crontab_write",
                      return_value=subprocess.CompletedProcess(args=[], returncode=0)):
        apply_cron(cfg, ex, NullReporter())

    con = sqlite3.connect(str(db))
    row = con.execute("SELECT value FROM settings WHERE key='poll_interval_mins'").fetchone()
    con.close()
    assert row[0] == "45"
