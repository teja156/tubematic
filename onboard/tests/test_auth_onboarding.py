"""The dashboard password and service tokens on the onboarding side (TMDEV-152):
the `auth` step, `--set-password`, `--rotate-tokens` and the Executor's two
secret operations.
"""
import os
import sqlite3
import stat
import subprocess

import pytest

from onboard import actions, auth_commands
from onboard.executor import Executor, NullReporter
from tubematic_core import auth

PASSWORD = "correct horse battery"


class _Rep(NullReporter):
    def __init__(self):
        self.oks, self.infos, self.warns = [], [], []

    def ok(self, msg):
        self.oks.append(msg)

    def info(self, msg):
        self.infos.append(msg)

    def warn(self, msg):
        self.warns.append(msg)


@pytest.fixture
def env(tmp_path, monkeypatch):
    db = tmp_path / "tubematic.db"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    sdir = tmp_path / "secrets"
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(sdir))
    monkeypatch.setattr(actions, "DB_PATH", db)
    monkeypatch.setattr(auth_commands, "DB_PATH", db)
    return db, sdir


# ── Executor ────────────────────────────────────────────────────────────────

def test_a_dry_run_names_the_directory_never_a_value(env):
    db, sdir = env
    ex = Executor(dry_run=True)
    ex.ensure_secrets()
    ex.rotate_secrets(["mcp_token"])
    assert [i.kind for i in ex.intents] == ["ensure_secrets", "rotate_secrets"]
    assert str(sdir) in ex.intents[0].detail
    assert not sdir.exists()


def test_the_executor_really_writes_when_not_dry(env):
    db, sdir = env
    assert sorted(Executor(dry_run=False).ensure_secrets()) == sorted(auth.SECRET_NAMES)
    assert stat.S_IMODE(os.stat(sdir).st_mode) == 0o700


# ── The auth step ───────────────────────────────────────────────────────────

def test_the_step_creates_tokens_and_asks_for_a_password(env, monkeypatch):
    db, sdir = env
    monkeypatch.setattr("onboard.prompt.ask_new_password", lambda: PASSWORD)
    actions.apply_auth(None, Executor(dry_run=False), _Rep())
    assert all((sdir / n).is_file() for n in auth.SECRET_NAMES)
    assert auth.verify_password(PASSWORD, auth.admin_password_hash(db))


def test_the_step_never_replaces_an_existing_password(env, monkeypatch):
    db, sdir = env
    auth.set_admin_password(db, PASSWORD)
    monkeypatch.setattr("onboard.prompt.ask_new_password",
                        lambda: pytest.fail("asked although a password is set"))
    rep = _Rep()
    actions.apply_auth(None, Executor(dry_run=False), rep)
    assert auth.verify_password(PASSWORD, auth.admin_password_hash(db))
    assert any("--set-password" in m for m in rep.oks)


def test_the_step_asks_nothing_and_writes_nothing_under_dry_run(env, monkeypatch):
    db, sdir = env
    monkeypatch.setattr("onboard.prompt.ask_new_password",
                        lambda: pytest.fail("asked under --dry-run"))
    actions.apply_auth(None, Executor(dry_run=True), _Rep())
    assert not sdir.exists()
    assert not auth.has_admin_password(db)


def test_the_hash_is_stored_never_the_password(env, monkeypatch):
    db, sdir = env
    monkeypatch.setattr("onboard.prompt.ask_new_password", lambda: PASSWORD)
    actions.apply_auth(None, Executor(dry_run=False), _Rep())
    con = sqlite3.connect(db)
    dump = "\n".join(con.iterdump())
    con.close()
    assert PASSWORD not in dump


# ── --set-password ──────────────────────────────────────────────────────────

def test_set_password_sets_a_first_password_without_touching_the_session_key(env):
    db, sdir = env
    auth.ensure_secrets(sdir)
    before = auth.read_secret("session_secret", sdir)
    assert auth_commands.run_set_password(rep=_Rep(), ex=Executor(dry_run=False),
                                          ask=lambda: PASSWORD) == 0
    assert auth.verify_password(PASSWORD, auth.admin_password_hash(db))
    assert auth.read_secret("session_secret", sdir) == before


def test_changing_the_password_signs_every_session_out(env):
    db, sdir = env
    auth.ensure_secrets(sdir)
    auth.set_admin_password(db, "the old password")
    before = auth.read_secret("session_secret", sdir)
    assert auth_commands.run_set_password(rep=_Rep(), ex=Executor(dry_run=False),
                                          ask=lambda: PASSWORD) == 0
    assert auth.verify_password(PASSWORD, auth.admin_password_hash(db))
    assert auth.read_secret("session_secret", sdir) != before


def test_set_password_works_before_an_upgrade(env):
    """Option A: a 1.2.x install has no secrets directory yet. The password is
    set anyway, and the upgrade creates the tokens afterwards."""
    db, sdir = env
    assert auth_commands.run_set_password(rep=_Rep(), ex=Executor(dry_run=False),
                                          ask=lambda: PASSWORD) == 0
    assert auth.has_admin_password(db)
    assert not sdir.exists()


def test_set_password_without_a_database_says_to_onboard(env, monkeypatch, tmp_path):
    monkeypatch.setattr(auth_commands, "DB_PATH", tmp_path / "missing.db")
    rep = _Rep()
    assert auth_commands.run_set_password(rep=rep, ex=Executor(dry_run=False),
                                          ask=lambda: pytest.fail("asked")) == 1
    assert any("onboard.py" in w for w in rep.warns)


def test_set_password_dry_run_asks_and_writes_nothing(env):
    db, sdir = env
    assert auth_commands.run_set_password(dry_run=True, rep=_Rep(),
                                          ask=lambda: pytest.fail("asked")) == 0
    assert not auth.has_admin_password(db)


# ── --rotate-tokens ─────────────────────────────────────────────────────────

class _OpenCode:
    @staticmethod
    def reload_argv(binary):
        return [binary, "reload"]


class _Claude:
    pass


def _agents(db, *rows):
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, binary TEXT, "
                "archived_at TEXT, created_at TEXT, models TEXT)")
    for aid, binary, archived in rows:
        con.execute("INSERT INTO agents VALUES (?, ?, ?, '2026', '[]')", (aid, binary, archived))
    con.commit()
    con.close()


def _rotate(env, monkeypatch, *, gate=True, run_rc=0):
    db, sdir = env
    calls = []
    ex = Executor(dry_run=False)
    monkeypatch.setattr(ex, "run", lambda cmd, **kw: calls.append(list(cmd))
                        or subprocess.CompletedProcess(cmd, run_rc, "", ""))
    monkeypatch.setattr("onboard.stack.gate", lambda *a, **kw: gate)
    rc = auth_commands.run_rotate_tokens(
        rep=_Rep(), ex=ex, lock_path=db.parent / "poll.lock",
        adapters={"opencode": _OpenCode, "claude": _Claude})
    return rc, calls


def test_rotation_replaces_every_token_in_place_and_restarts_their_readers(env, monkeypatch):
    db, sdir = env
    auth.ensure_secrets(sdir)
    before = {n: (auth.read_secret(n, sdir), os.stat(sdir / n).st_ino) for n in auth.SECRET_NAMES}
    rc, calls = _rotate(env, monkeypatch)
    assert rc == 0
    for n in auth.SECRET_NAMES:
        assert auth.read_secret(n, sdir) != before[n][0]
        assert os.stat(sdir / n).st_ino == before[n][1]
    assert ["docker", "compose", "restart", "tubematic-api", "tubematic-mcp",
            "tubematic-dashboard"] in calls


def test_rotation_reloads_only_agents_that_cache_the_token(env, monkeypatch):
    db, sdir = env
    auth.ensure_secrets(sdir)
    _agents(db, ("opencode", "/b/opencode", None), ("claude", "/b/claude", None))
    rc, calls = _rotate(env, monkeypatch)
    assert ["/b/opencode", "reload"] in calls
    assert not any(c[0] == "/b/claude" for c in calls)


def test_an_archived_agent_is_not_reloaded(env, monkeypatch):
    db, sdir = env
    auth.ensure_secrets(sdir)
    _agents(db, ("opencode", "/b/opencode", "2026-01-01"))
    rc, calls = _rotate(env, monkeypatch)
    assert ["/b/opencode", "reload"] not in calls


def test_work_in_flight_stops_the_rotation_before_anything_changes(env, monkeypatch):
    db, sdir = env
    auth.ensure_secrets(sdir)
    before = {n: auth.read_secret(n, sdir) for n in auth.SECRET_NAMES}
    rc, calls = _rotate(env, monkeypatch, gate=False)
    assert rc == 1 and calls == []
    assert {n: auth.read_secret(n, sdir) for n in auth.SECRET_NAMES} == before


def test_rotation_with_no_tokens_yet_says_how_to_create_them(env, monkeypatch):
    rep = _Rep()
    assert auth_commands.run_rotate_tokens(rep=rep, ex=Executor(dry_run=False),
                                           adapters={}) == 1
    assert any("onboard.py" in w for w in rep.warns)


# ── The post-install checklist ──────────────────────────────────────────────

from onboard import checks  # noqa: E402


def test_the_checklist_reports_a_missing_password_and_tokens(env):
    db, sdir = env
    items = {c.label.split(" (")[0]: c for c in checks.auth_items(db)}
    assert items["Dashboard password set"].ok is False
    assert items["Service tokens"].ok is False
    assert "--step auth" in items["Service tokens"].hint


def test_the_checklist_passes_a_complete_setup(env):
    db, sdir = env
    auth.ensure_secrets(sdir)
    auth.set_admin_password(db, PASSWORD)
    assert all(c.ok for c in checks.auth_items(db))


def test_a_world_readable_secrets_directory_is_a_warning(env):
    db, sdir = env
    auth.ensure_secrets(sdir)
    os.chmod(sdir, 0o755)
    item = next(c for c in checks.auth_items(db) if "0700" in c.label)
    assert item.ok is False and item.severity == "warning"


def test_the_helper_check_runs_the_real_helper(env):
    import shlex
    import sys
    from onboard.agent_install import REPO_ROOT
    db, sdir = env
    helper = f"{shlex.quote(sys.executable)} {shlex.quote(str(REPO_ROOT / 'scripts' / 'mcp_auth_header.py'))}"
    assert checks._helper_prints_a_header(helper) is False      # no token yet
    auth.ensure_secrets(sdir)
    assert checks._helper_prints_a_header(helper) is True
    assert checks._helper_prints_a_header("/no/such/binary") is False


def _fake_server(monkeypatch, without, with_token):
    import urllib.error
    import urllib.request

    class _Resp:
        def __init__(self, status):
            self.status = status

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def urlopen(req, timeout=None):
        code = with_token if req.get_header("Authorization") else without
        if code is None:
            raise urllib.error.URLError("refused")
        if code >= 400:
            raise urllib.error.HTTPError(req.full_url, code, "x", {}, None)
        return _Resp(code)

    monkeypatch.setattr(urllib.request, "urlopen", urlopen)


@pytest.mark.parametrize("without,with_token,expected", [
    (401, 200, (True, True)),       # protected and our token works
    (200, 200, (False, True)),      # an MCP server still running without auth
    (401, 401, (True, False)),      # the server holds an older token
    (None, None, (None, None)),     # stack down: unknown, never "open"
])
def test_the_live_mcp_probe(env, monkeypatch, without, with_token, expected):
    db, sdir = env
    auth.ensure_secrets(sdir)
    _fake_server(monkeypatch, without, with_token)
    assert checks.mcp_auth_probe() == expected


def test_a_failed_restart_fails_the_rotation(env, monkeypatch):
    """Codex review P2. The files are already replaced, so the API and MCP still
    hold the old tokens while the dashboard and the agents read the new ones —
    nothing authenticates. A zero exit would tell automation it worked."""
    db, sdir = env
    auth.ensure_secrets(sdir)
    rc, calls = _rotate(env, monkeypatch, run_rc=1)
    assert rc == 1


def test_a_failed_reload_fails_the_rotation(env, monkeypatch):
    db, sdir = env
    auth.ensure_secrets(sdir)
    _agents(db, ("opencode", "/b/opencode", None))
    ex = Executor(dry_run=False)
    calls = []

    def run(cmd, **kw):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(cmd, 1 if cmd[-1] == "reload" else 0, "", "")

    monkeypatch.setattr(ex, "run", run)
    monkeypatch.setattr("onboard.stack.gate", lambda *a, **kw: True)
    rep = _Rep()
    rc = auth_commands.run_rotate_tokens(rep=rep, ex=ex, lock_path=db.parent / "poll.lock",
                                         adapters={"opencode": _OpenCode})
    assert rc == 1
    assert any("not finished" in w for w in rep.warns)
