"""onboard/stack.py — stack control shared by upgrade.py and scripts/service.py
(TMDEV-96).

The in-flight gate exists to stop an upgrade or a restart from killing work
that costs money to redo: a render (counted as a failure, and one failure
with the default retry budget of 1 escalates the video to FAILED), a voicing
(ElevenLabs already billed, nothing reconciles VOICING on restart), an agent
session (it holds poll.lock), or a publish upload still in flight.
"""
import fcntl
import importlib.util
import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest

from onboard import stack
from onboard.config import DATA_ROOT
from onboard.executor import Executor, NullReporter
from tubematic_core import db as tdb

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-09-19T00:00:00Z"


class _Rep(NullReporter):
    def __init__(self):
        self.oks, self.infos, self.warns, self.fails = [], [], [], []
    def ok(self, msg, *a, **k): self.oks.append(msg)
    def info(self, msg, *a, **k): self.infos.append(msg)
    def warn(self, msg, *a, **k): self.warns.append(msg)
    def fail(self, msg, *a, **k):
        self.fails.append(msg)
        raise RuntimeError(msg)


def _db(tmp_path, videos=(), publications=()):
    path = tmp_path / "tubematic.db"
    tdb.migrate(path, backup=False)
    con = sqlite3.connect(path)
    for vid, status in videos:
        con.execute("INSERT INTO videos (id, topic, title, status, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (vid, f"topic {vid}", f"title {vid}", status,
                                                  NOW, NOW))
    for pid, vid, post_id in publications:
        con.execute("INSERT INTO video_publications (id, video_id, platform, social_account_id, "
                    "postforme_post_id, created_at, updated_at) VALUES (?, ?, 'youtube', 'acc', "
                    "?, ?, ?)", (pid, vid, post_id, NOW, NOW))
    con.commit()
    con.close()
    return path


# ── in_flight ────────────────────────────────────────────────────────────────

def test_a_clean_database_has_nothing_in_flight(tmp_path):
    path = _db(tmp_path, videos=[("v1", "VIDEO_READY"), ("v2", "RENDER_QUEUED")])
    assert stack.in_flight(path) == []


def test_a_missing_database_has_nothing_in_flight(tmp_path):
    assert stack.in_flight(tmp_path / "nope.db") == []


@pytest.mark.parametrize("status", ["RENDERING", "VOICING"])
def test_rendering_and_voicing_videos_are_in_flight(tmp_path, status):
    path = _db(tmp_path, videos=[("vid_a", status)])
    reasons = stack.in_flight(path)
    assert len(reasons) == 1
    assert "vid_a" in reasons[0] and status in reasons[0]


def test_a_publish_whose_upload_has_not_finished_is_in_flight(tmp_path):
    """Publication rows are written at the claim with an empty post id; the id
    is filled once postforme has the post. Empty means the upload is running
    inside a Flask request that a stop would kill."""
    path = _db(tmp_path, videos=[("vid_p", "PUBLISHING")],
               publications=[("p1", "vid_p", ""), ("p2", "vid_p", "")])
    reasons = stack.in_flight(path)
    assert len(reasons) == 1 and "vid_p" in reasons[0]


def test_a_publish_with_no_rows_yet_is_in_flight(tmp_path):
    """Before 1.0.1 the rows were written only after the upload finished, so an
    install still running that code shows an upload in progress as PUBLISHING
    with no rows at all — the very state an upgrade to 1.0.1 meets. Current
    code writes the rows in the claim's transaction, so nothing else looks
    like this."""
    path = _db(tmp_path, videos=[("vid_old", "PUBLISHING")])
    reasons = stack.in_flight(path)
    assert len(reasons) == 1 and "vid_old" in reasons[0]


def test_a_publish_already_handed_to_postforme_is_not_in_flight(tmp_path):
    """Once every row has a post id the worker only polls, and polling
    survives a restart."""
    path = _db(tmp_path, videos=[("vid_p", "PUBLISHING")],
               publications=[("p1", "vid_p", "post_1")])
    assert stack.in_flight(path) == []


@pytest.mark.skipif(os.geteuid() == 0, reason="root reads any file")
def test_an_unreadable_database_is_reported_plainly_and_blocks(tmp_path):
    """WAL needs write access to the -shm sidecar even to read, so a user who
    cannot write the database cannot read it either. That must read as an
    instruction, not a raw SQLite error — and it must block, since nothing
    can be verified."""
    path = _db(tmp_path, videos=[("v1", "VIDEO_READY")])
    path.chmod(0)
    try:
        reasons = stack.in_flight(path)
    finally:
        path.chmod(0o644)
    assert len(reasons) == 1
    assert "cannot read the database" in reasons[0]
    assert "sqlite3" not in reasons[0]


# ── poll lock ────────────────────────────────────────────────────────────────

def test_the_lock_is_the_one_poll_py_takes():
    """A different path would exclude nothing. Keep in sync: scripts/poll.py."""
    spec = importlib.util.spec_from_file_location("scripts_config",
                                                  REPO_ROOT / "scripts" / "config.py")
    cfg = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cfg)
    poll_src = (REPO_ROOT / "scripts" / "poll.py").read_text()
    assert 'LOCKFILE           = POLL_LOG_DIR.parent / "poll.lock"' in poll_src
    assert stack.LOCK_PATH == cfg.POLL_LOG_DIR.parent / "poll.lock"


def test_the_lock_is_acquired_when_free_and_the_file_survives(tmp_path):
    lock = tmp_path / "agent" / "poll.lock"
    with stack.poll_lock(lock) as acquired:
        assert acquired
        # Held: a second non-blocking attempt, as poll.py makes, must fail.
        with open(lock, "w") as fh, pytest.raises(BlockingIOError):
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert lock.exists()  # never unlinked, same reason as poll.py


def test_a_held_lock_is_reported_not_waited_on(tmp_path):
    lock = tmp_path / "poll.lock"
    with open(lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with stack.poll_lock(lock) as acquired:
            assert acquired is False


# ── gate ─────────────────────────────────────────────────────────────────────

def test_the_gate_passes_with_the_lock_and_nothing_in_flight(tmp_path):
    rep = _Rep()
    assert stack.gate(_db(tmp_path), lock_acquired=True, force=False, rep=rep)
    assert rep.warns == []


def test_the_gate_refuses_on_in_flight_work(tmp_path):
    rep = _Rep()
    path = _db(tmp_path, videos=[("vid_r", "RENDERING")])
    assert not stack.gate(path, lock_acquired=True, force=False, rep=rep)
    assert any("vid_r" in w for w in rep.warns)


def test_the_gate_refuses_while_an_agent_holds_the_lock(tmp_path):
    rep = _Rep()
    assert not stack.gate(_db(tmp_path), lock_acquired=False, force=False, rep=rep)
    assert any("poll.lock" in w for w in rep.warns)


def test_the_gate_refuses_on_a_session_a_dead_poller_left_running(tmp_path):
    """The poller's sessions outlive it by design (TMDEV-129). With the lock
    free nothing else would see one, and stopping the stack would pull the MCP
    server out from under it mid-session."""
    proc = subprocess.Popen(["sleep", "30"])
    try:
        registry = tmp_path / "poll-sessions.json"
        registry.write_text(json.dumps([{"pid": proc.pid, "label": "video=vid_o",
                                         "proc_start": stack._proc_start(proc.pid)}]))
        rep = _Rep()
        assert not stack.gate(_db(tmp_path), lock_acquired=True, force=False, rep=rep,
                              registry=registry)
        assert any("video=vid_o" in w for w in rep.warns)
    finally:
        proc.kill()
        proc.wait()
    # Gone now: the same registry no longer blocks anything.
    assert stack.gate(_db(tmp_path), lock_acquired=True, force=False, rep=_Rep(),
                      registry=registry)


def test_a_reused_pid_in_the_registry_is_not_a_running_session(tmp_path):
    registry = tmp_path / "poll-sessions.json"
    registry.write_text(json.dumps([{"pid": os.getpid(), "label": "video=v",
                                     "proc_start": "1"}]))
    assert stack.orphan_sessions(registry) == []
    registry.write_text("not json")
    assert stack.orphan_sessions(registry) == []


def test_the_registry_is_the_one_poll_py_writes():
    poll_src = (REPO_ROOT / "scripts" / "poll.py").read_text()
    assert 'REGISTRY             = POLL_LOG_DIR.parent / "poll-sessions.json"' in poll_src
    # Read as source: an autouse fixture points the live value at tmp_path.
    stack_src = (REPO_ROOT / "onboard" / "stack.py").read_text()
    assert 'SESSIONS_REGISTRY = POLL_LOG_DIR.parent / "poll-sessions.json"' in stack_src


def test_force_passes_the_gate_but_still_names_the_work(tmp_path):
    rep = _Rep()
    path = _db(tmp_path, videos=[("vid_r", "RENDERING")])
    assert stack.gate(path, lock_acquired=False, force=True, rep=rep)
    assert any("vid_r" in w for w in rep.warns)
    assert any("--force" in w for w in rep.warns)


# ── stop / start ─────────────────────────────────────────────────────────────

def test_stop_stops_and_never_removes(monkeypatch):
    ex = Executor(dry_run=True)
    stack.stop(ex, _Rep())
    cmds = [i.detail for i in ex.intents if i.kind == "run"]
    assert cmds == ["docker compose stop"]


def test_start_creates_directories_and_reconciles_volumes_before_up(monkeypatch):
    """A bind volume whose device path is missing fails the mount, and a stale
    device must be dropped before `up` or Compose keeps the old one."""
    calls = []

    def dirs(cfg, ex, rep):
        calls.append("directories")
        ex.mkdir(DATA_ROOT / "data")

    def reconcile(ex, rep):
        calls.append("reconcile")
        ex.run(["docker", "volume", "rm", "tubematic_db-data"])

    monkeypatch.setattr(stack, "apply_directories", dirs)
    monkeypatch.setattr(stack, "_reconcile_volume_devices", reconcile)
    monkeypatch.setattr(stack, "_stale_volumes", lambda: [])
    ex = Executor(dry_run=True)
    stack.start(ex, _Rep(), confirm_down=lambda n: True)
    assert calls == ["directories", "reconcile"]
    kinds = [(i.kind, i.detail) for i in ex.intents]
    assert kinds[0][0] == "mkdir"
    # Compose refuses to start a service whose token file is missing (TMDEV-152).
    assert kinds[1] == ("run", "docker volume rm tubematic_db-data")
    assert kinds[2][0] == "ensure_secrets"
    assert kinds[3] == ("run", "docker compose up -d")


def test_start_can_name_services(monkeypatch):
    monkeypatch.setattr(stack, "apply_directories", lambda cfg, ex, rep: None)
    monkeypatch.setattr(stack, "_reconcile_volume_devices", lambda ex, rep: None)
    monkeypatch.setattr(stack, "_stale_volumes", lambda: [])
    ex = Executor(dry_run=True)
    stack.start(ex, _Rep(), services=["tubematic-renderer"], confirm_down=lambda n: True)
    assert [i.detail for i in ex.intents if i.kind == "run"] == \
        ["docker compose up -d tubematic-renderer"]


def test_a_failed_up_fails_loudly(monkeypatch):
    monkeypatch.setattr(stack, "apply_directories", lambda cfg, ex, rep: None)
    monkeypatch.setattr(stack, "_reconcile_volume_devices", lambda ex, rep: None)
    monkeypatch.setattr(stack, "_stale_volumes", lambda: [])
    ex = Executor(dry_run=False)
    monkeypatch.setattr(ex, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 1, "", "boom"))
    rep = _Rep()
    with pytest.raises(RuntimeError):
        stack.start(ex, rep, confirm_down=lambda n: True)
    assert rep.fails


# ── cron helpers ─────────────────────────────────────────────────────────────

CRON = ("MAILTO=\"\"\n# Tubematic — managed by onboard.py — do not edit manually\n"
        "*/30 * * * * /opt/old/.venv/bin/python3 /opt/old/scripts/poll.py "
        ">> /home/u/.tubematic-agent/logs/cron.log 2>&1\n")


def test_the_poll_line_and_its_install_directory_are_read_from_the_crontab():
    line = stack.poll_cron_line(CRON)
    assert line.startswith("*/30")
    assert stack.install_dir_of(line) == Path("/opt/old")
    assert stack.python_of(line) == "/opt/old/.venv/bin/python3"


def test_no_poll_line_means_no_install_directory():
    assert stack.poll_cron_line("0 1 * * * backup.sh\n") is None
    assert stack.install_dir_of(None) is None


# ── report ───────────────────────────────────────────────────────────────────

def _no_docker(cmd, **kw):
    raise FileNotFoundError(cmd[0])


def test_report_survives_a_half_configured_install(tmp_path, monkeypatch):
    """--check is what a person runs when unsure the upgrade worked, so it
    must report on a machine with no database, no crontab and no docker
    rather than crash."""
    monkeypatch.setattr(stack.subprocess, "run", _no_docker)
    rep = _Rep()
    ok = stack.report(rep, db_path=tmp_path / "missing.db", repo_root=tmp_path, mode="release")
    assert ok is False
    text = " ".join(rep.oks + rep.infos + rep.warns)
    assert "database" in text and "cron" in text.lower() and "docker" in text.lower()


def test_report_flags_a_cron_line_pointing_at_another_install(tmp_path, monkeypatch):
    path = _db(tmp_path)

    def run(cmd, **kw):
        if cmd[:2] == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, CRON, "")
        if cmd[0] == "docker":
            return subprocess.CompletedProcess(cmd, 0, "running healthy\n", "")
        raise AssertionError(cmd)

    monkeypatch.setattr(stack.subprocess, "run", run)
    rep = _Rep()
    assert stack.report(rep, db_path=path, repo_root=tmp_path, mode="release") is False
    assert any("/opt/old" in w for w in rep.warns)


def test_report_is_clean_on_a_healthy_install(tmp_path, monkeypatch):
    path = _db(tmp_path)
    py = tmp_path / ".venv" / "bin" / "python3"
    py.parent.mkdir(parents=True)
    py.touch()
    cron = f"*/30 * * * * {py} {tmp_path}/scripts/poll.py >> /x/cron.log 2>&1\n"

    def run(cmd, **kw):
        if cmd[:2] == ["crontab", "-l"]:
            return subprocess.CompletedProcess(cmd, 0, cron, "")
        return subprocess.CompletedProcess(cmd, 0, "running healthy\n", "")

    monkeypatch.setattr(stack.subprocess, "run", run)
    rep = _Rep()
    assert stack.report(rep, db_path=path, repo_root=tmp_path, mode="release") is True, rep.warns
    assert rep.warns == []


# ── Review fixes: reconciliation can take the whole stack down ───────────────

STALE = [("tubematic_db-data", "/old/data", "/new/data")]


def _start_env(monkeypatch, stale, running):
    calls = []
    monkeypatch.setattr(stack, "apply_directories", lambda cfg, ex, rep: None)
    monkeypatch.setattr(stack, "_stale_volumes", lambda: stale)
    monkeypatch.setattr(stack, "_reconcile_volume_devices",
                        lambda ex, rep: calls.append("reconcile") if stale else None)
    monkeypatch.setattr(stack, "_container_state",
                        lambda name: ("running", "") if name in running else ("exited", ""))
    return calls


def test_a_stale_volume_with_the_stack_up_asks_before_taking_it_down(monkeypatch):
    """Reconciling runs `docker compose down`, which kills every container —
    a render included — even when only one service was asked for."""
    calls = _start_env(monkeypatch, STALE, running={"tubematic-renderer"})
    asked = []
    ex = Executor(dry_run=True)
    with pytest.raises(RuntimeError):
        stack.start(ex, _Rep(), ["tubematic-dashboard"],
                    confirm_down=lambda names: asked.append(names) or False)
    assert asked == [["tubematic-renderer"]]
    assert calls == [] and ex.intents == []


def test_after_a_reconcile_every_service_comes_back_not_just_the_named_one(monkeypatch):
    calls = _start_env(monkeypatch, STALE, running={"tubematic-api"})
    ex = Executor(dry_run=True)
    stack.start(ex, _Rep(), ["tubematic-dashboard"], confirm_down=lambda names: True)
    assert calls == ["reconcile"]
    assert [i.detail for i in ex.intents if i.kind == "run"] == ["docker compose up -d"]


@pytest.mark.parametrize("stale, running", [([], {"tubematic-api"}), (STALE, set())])
def test_no_question_when_nothing_would_be_taken_down(monkeypatch, stale, running):
    _start_env(monkeypatch, stale, running)
    ex = Executor(dry_run=True)
    stack.start(ex, _Rep(), ["tubematic-dashboard"],
                confirm_down=lambda names: pytest.fail("asked needlessly"))
    assert ex.intents[-1].detail.startswith("docker compose up -d")


# ── Review fixes: a requested service that did not start is a failure ────────

def _live_start(monkeypatch, states, health_ok=True):
    _start_env(monkeypatch, [], running=set())
    monkeypatch.setattr(stack, "_container_state", lambda name: states.get(name, ("", "")))
    monkeypatch.setattr(stack, "_await_health", lambda name, url, rep: health_ok)
    ex = Executor(dry_run=False)
    monkeypatch.setattr(ex, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 0, "", ""))
    return ex


def test_a_renderer_that_exited_fails_the_start(monkeypatch):
    ex = _live_start(monkeypatch, {"tubematic-renderer": ("exited", "")})
    with pytest.raises(RuntimeError):
        stack.start(ex, _Rep(), ["tubematic-renderer"], confirm_down=lambda n: True)


def test_an_unhealthy_dashboard_fails_the_start(monkeypatch):
    ex = _live_start(monkeypatch, {"tubematic-dashboard": ("running", "unhealthy")},
                     health_ok=False)
    with pytest.raises(RuntimeError):
        stack.start(ex, _Rep(), ["tubematic-dashboard"], confirm_down=lambda n: True)


def test_a_healthy_start_succeeds(monkeypatch):
    ex = _live_start(monkeypatch, {"tubematic-renderer": ("running", "")})
    stack.start(ex, _Rep(), [], confirm_down=lambda n: True)


# ── Review fixes: a database newer than this code is not healthy ─────────────

def test_a_database_newer_than_this_version_is_incompatible(tmp_path, monkeypatch):
    """Older code may not understand a renamed or dropped column — rollback
    restores the matching backup for exactly this reason."""
    path = _db(tmp_path)
    con = sqlite3.connect(path)
    con.execute("INSERT INTO schema_migrations (version, name, applied_at) "
                "VALUES (9999, 'future', ?)", (NOW,))
    con.commit()
    con.close()
    monkeypatch.setattr(stack.subprocess, "run", _no_docker)
    rep = _Rep()
    assert stack.report(rep, db_path=path, repo_root=tmp_path, mode="release") is False
    assert any("newer" in w for w in rep.warns)
    assert not any("schema" in o.lower() for o in rep.oks)
