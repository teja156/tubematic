"""scripts/service.py — start, stop, restart, status and logs (TMDEV-96).

`start` exists so nobody needs a bare `docker compose up -d`, which skips the
data directories and the volume reconciliation onboarding does. `stop` and
`restart` run the same in-flight gate as upgrade.py, because a restart kills a
render exactly as an upgrade does.
"""
import os
import importlib.util
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import onboard.stack as stack  # noqa: E402
from onboard.executor import Executor, Intent, NullReporter  # noqa: E402
from tubematic_core import db as tdb  # noqa: E402

NOW = "2026-09-19T00:00:00Z"


@pytest.fixture
def service():
    spec = importlib.util.spec_from_file_location("service_entry",
                                                  REPO_ROOT / "scripts" / "service.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Rep(NullReporter):
    def __init__(self):
        self.lines = []
    def ok(self, msg, *a, **k): self.lines.append(msg)
    def info(self, msg, *a, **k): self.lines.append(msg)
    def warn(self, msg, *a, **k): self.lines.append(msg)
    def fail(self, msg, *a, **k):
        self.lines.append(msg)
        raise RuntimeError(msg)


@pytest.fixture
def env(tmp_path, monkeypatch, service):
    db_path = tmp_path / "tubematic.db"
    tdb.migrate(db_path, backup=False)

    def step(name):
        def fn(*args, **kwargs):
            ex = next(a for a in args if isinstance(a, Executor))
            ex.intents.append(Intent("step", name))
        return fn

    monkeypatch.setattr(stack, "apply_directories", step("directories"))
    monkeypatch.setattr(stack, "_reconcile_volume_devices", step("reconcile"))
    monkeypatch.setattr(stack, "_stale_volumes", lambda: [])

    def run(command, **kw):
        rep, ex = _Rep(), Executor(dry_run=True)
        code = service.run(command, db_path=db_path, lock_path=tmp_path / "poll.lock",
                                  rep=rep, ex=ex, **kw)
        return code, [i.detail for i in ex.intents], " ".join(rep.lines)

    class Env:
        pass
    e = Env()
    e.db_path, e.run = db_path, run
    return e


def _rendering(db_path):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('vid_r', 't', 'RENDERING', ?, ?)", (NOW, NOW))
    con.commit()
    con.close()


def test_start_goes_through_directories_and_volume_reconciliation(env):
    code, order, _ = env.run("start")
    assert code == 0
    # Any missing service token is created right before `up` (TMDEV-152).
    secrets = os.environ["TUBEMATIC_SECRETS_DIR"]
    assert order == ["directories", "reconcile", secrets, "docker compose up -d"]


def test_start_one_service(env):
    _, order, _ = env.run("start", service="tubematic-renderer")
    assert order[-1] == "docker compose up -d tubematic-renderer"


def test_stop_stops(env):
    code, order, _ = env.run("stop")
    assert code == 0
    assert order == ["docker compose stop"]


def test_restart_is_stop_then_start(env):
    code, order, _ = env.run("restart", service="tubematic-api")
    assert code == 0
    assert order == ["docker compose stop tubematic-api", "directories", "reconcile",
                     os.environ["TUBEMATIC_SECRETS_DIR"], "docker compose up -d tubematic-api"]


@pytest.mark.parametrize("command", ["stop", "restart"])
def test_stop_and_restart_refuse_while_a_render_is_running(env, command):
    _rendering(env.db_path)
    code, order, text = env.run(command)
    assert code == 1
    assert order == []
    assert "vid_r" in text


def test_force_overrides_the_gate(env):
    _rendering(env.db_path)
    code, order, _ = env.run("stop", force=True)
    assert code == 0
    assert order == ["docker compose stop"]


def test_the_dashboard_alone_is_not_gated(env):
    """It holds no work: restarting it cannot kill a render or a voicing."""
    _rendering(env.db_path)
    code, order, _ = env.run("restart", service="tubematic-dashboard")
    assert code == 0
    assert order[0] == "docker compose stop tubematic-dashboard"


@pytest.mark.parametrize("command, svc", [("start", None), ("restart", "tubematic-dashboard")])
def test_a_volume_reconcile_that_would_take_the_stack_down_is_gated(env, monkeypatch,
                                                                    command, svc):
    """Re-pointing a moved volume runs `compose down` on every container, so a
    start — or a dashboard-only restart, normally ungated — must not do it
    while a render is running."""
    _rendering(env.db_path)
    monkeypatch.setattr(stack, "_stale_volumes", lambda: [("tubematic_db-data", "/a", "/b")])
    monkeypatch.setattr(stack, "_container_state", lambda name: ("running", ""))
    code, order, text = env.run(command, service=svc)
    assert code == 1
    assert order == []  # refused before anything stopped — nothing left half done
    assert "vid_r" in text


def test_status_is_the_shared_report(env, monkeypatch):
    seen = []
    monkeypatch.setattr(stack, "report", lambda rep, **kw: seen.append(kw) or False)
    code, order, _ = env.run("status")
    assert code == 1 and seen and order == []


def test_logs_hands_over_to_docker_compose(env, service, monkeypatch):
    execs = []
    monkeypatch.setattr(service.os, "execvp", lambda f, argv: execs.append(argv))
    monkeypatch.setattr(service.os, "chdir", lambda p: None)
    env.run("logs", service="tubematic-renderer", follow=True)
    assert execs == [["docker", "compose", "logs", "--tail", "200", "-f",
                      "tubematic-renderer"]]


def _main(service, monkeypatch, *args):
    monkeypatch.setattr(service, "_bootstrap", lambda: None)
    calls = []
    monkeypatch.setattr(service, "run", lambda command, **kw: calls.append((command, kw)) or 0)
    monkeypatch.setattr(sys, "argv", ["service.py", *args])
    try:
        service.main()
    except SystemExit as exc:
        return exc.code, calls
    return 0, calls


def test_the_command_line_parses_into_run(service, monkeypatch):
    code, calls = _main(service, monkeypatch, "restart", "tubematic-api", "--force", "--dry-run")
    assert code == 0
    assert calls == [("restart", {"service": "tubematic-api", "follow": False, "force": True,
                                  "dry_run": True})]


@pytest.mark.parametrize("argv", [[], ["reboot"], ["start", "tubematic-nope"], ["stop", "--yes"]])
def test_bad_arguments_are_refused(service, monkeypatch, argv):
    code, calls = _main(service, monkeypatch, *argv)
    assert code == 1 and calls == []
