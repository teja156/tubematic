"""onboard/agent_install.py — `python onboard.py --install-agent <name>` (TMDEV-90).

Nothing here runs a real agent CLI: every subprocess is stubbed, because a
model probe for a *valid* model is a real (billed) run, and the auth check
reads the host's own login.
"""
import json
import shlex
import sqlite3
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from onboard import actions, agent_install, api_keys
from onboard.executor import Executor, NullReporter
from tubematic_core import db as tdb

REPO_ROOT = Path(__file__).resolve().parents[2]
CLAUDE = agent_install.ADAPTERS["claude"]
CODEX = agent_install.ADAPTERS["codex"]
OPENCODE = agent_install.ADAPTERS["opencode"]


# ── The third schema copy ────────────────────────────────────────────────────

def _table_columns(con: sqlite3.Connection, table: str) -> list:
    """A table's real column definitions, as SQLite itself will enforce them:
    (cid, name, declared type, NOT NULL, default, primary-key rank). This is
    read off a live table, never re-parsed out of CREATE TABLE source text."""
    return con.execute(f"PRAGMA table_info({table})").fetchall()


def test_the_onboard_schema_copy_matches(tmp_path, monkeypatch):
    """Keep-in-sync pinned mechanically: the installer creates the `agents`
    table itself on a fresh host, before any container has necessarily
    started, so it can't just import the schema from a running process.

    This assertion's basis has moved twice before, and both moves looked
    like the fix at the time — worth recording so a third "simplification"
    doesn't undo this one too:

    1. Originally compared AGENTS_SCHEMA against renderer/api/pipeline.py's
       and mcp/server.py's own copies of the same DDL. All three could
       drift together and this test would never notice, since none of them
       was ever checked against a real database.
    2. TMDEV-91 deleted both of those copies in favor of
       tubematic_core/migrations/, so the test switched to comparing
       AGENTS_SCHEMA against the CREATE TABLE text inside
       0001_baseline.py's *source*, extracted with a parenthesis-balancing
       helper.

    (2) is still the wrong basis, for a reason (1) never had to face: a real
    database is shaped by every migration that has ever run against it, not
    just 0001. A later migration doing e.g. `ALTER TABLE agents ADD COLUMN
    foo` leaves 0001's file text completely untouched, so comparing against
    that text would keep passing while every actually-migrated database
    grows a column AGENTS_SCHEMA knows nothing about — exactly the failure
    this test exists to catch.

    So this builds a real, fully migrated database via tubematic_core.db's
    own migrate() (which walks the whole migration chain, not just 0001)
    and reads its `agents` table with PRAGMA table_info — the one place
    that reflects the schema as it actually ends up, migrations and all.
    AGENTS_SCHEMA is applied to a throwaway database and read the same way,
    so the comparison is PRAGMA-result vs PRAGMA-result, not text vs text.
    That also catches a changed type or default, not just an added or
    removed column name. Do not "simplify" this back to reading a
    migration file's source text.
    """
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))
    migrated_path = tmp_path / "migrated.db"
    tdb.migrate(migrated_path)
    migrated_con = sqlite3.connect(migrated_path)
    try:
        real = _table_columns(migrated_con, "agents")
    finally:
        migrated_con.close()

    onboard_con = sqlite3.connect(":memory:")
    try:
        onboard_con.execute(agent_install.AGENTS_SCHEMA)
        onboard = _table_columns(onboard_con, "agents")
    finally:
        onboard_con.close()

    assert onboard == real


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def db(tmp_path, monkeypatch):
    path = tmp_path / "tubematic.db"
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    monkeypatch.setattr(agent_install, "DB_PATH", path)
    return path


def _agent(db, agent_id="claude"):
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM agents WHERE id = ?", (agent_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def _settings(db):
    con = sqlite3.connect(db)
    rows = dict(con.execute("SELECT key, value FROM settings").fetchall())
    con.close()
    return rows


def _write(db, *, models=("opus",), verified=True, dry_run=False, scope="user", ws="/srv/ws"):
    agent_install.write_agent_row(
        CLAUDE, "/usr/local/bin/claude", {"INSTALL_SCOPE": scope}, Path(ws), list(models),
        verified=verified, ex=Executor(dry_run=dry_run))


class _Rec(NullReporter):
    def __init__(self):
        self.msgs = []

    def ok(self, m):
        self.msgs.append(("ok", m))

    def warn(self, m):
        self.msgs.append(("warn", m))

    def info(self, m):
        self.msgs.append(("info", m))

    def text(self):
        return "\n".join(m for _, m in self.msgs)


# ── Pre-fill ────────────────────────────────────────────────────────────────

def test_a_fresh_install_prefills_the_defaults(db):
    values = agent_install.current_values("claude", db)
    assert values == {"INSTALL_SCOPE": "user",
                      "AGENT_RUN_PATH": agent_install.default_run_path("claude"),
                      "WIPE_AGENT_WORKSPACE": "false", "AGENT_MODELS": "[]",
                      "AGENT_EFFORT": "high"}


def test_an_upgrade_prefills_from_the_retired_settings_rows(db):
    con = sqlite3.connect(db)
    con.executemany("INSERT INTO settings VALUES (?, ?)",
                    [("install_scope", "project"), ("agent_run_path", "/srv/old-ws")])
    con.commit()
    con.close()
    values = agent_install.current_values("claude", db)
    assert values["INSTALL_SCOPE"] == "project"
    assert values["AGENT_RUN_PATH"] == "/srv/old-ws"


def test_a_re_run_prefills_from_the_agents_own_row(db):
    _write(db, models=("sonnet", "opus"), scope="project", ws="/srv/claude")
    values = agent_install.current_values("claude", db)
    assert json.loads(values["AGENT_MODELS"]) == ["sonnet", "opus"]
    assert values["INSTALL_SCOPE"] == "project"
    assert values["AGENT_RUN_PATH"] == "/srv/claude"
    assert values["WIPE_AGENT_WORKSPACE"] == "false"   # ephemeral, never stored


# ── Workspace layout ────────────────────────────────────────────────────────

@pytest.fixture
def logs(tmp_path, monkeypatch):
    path = tmp_path / "ta" / "logs"
    monkeypatch.setattr(agent_install, "POLL_LOG_DIR", path)
    return path


def _opencode_agent_row(db, run_path, *, archived_at=None):
    """An installed `opencode` row pointing at `run_path`."""
    con = sqlite3.connect(db)
    con.execute(agent_install.AGENTS_SCHEMA)
    con.execute("INSERT INTO agents (id, name, binary, run_path, models, archived_at, "
                "created_at, updated_at) VALUES ('opencode', 'OpenCode', '/b/opencode', ?, "
                "'[\"m\"]', ?, 'x', 'x')", (str(run_path), archived_at))
    con.commit()
    con.close()


def _other_agent(db, run_path, *, archived_at=None):
    con = sqlite3.connect(db)
    con.execute(agent_install.AGENTS_SCHEMA)
    con.execute("INSERT INTO agents (id, name, binary, run_path, archived_at, created_at, "
                "updated_at) VALUES ('codex', 'Codex', '/b/codex', ?, ?, 'x', 'x')",
                (str(run_path), archived_at))
    con.commit()
    con.close()


def test_each_agent_defaults_to_its_own_directory_beside_the_logs(logs):
    assert agent_install.default_run_path("claude") == str(logs.parent / "claude")
    assert agent_install.default_run_path("codex") == str(logs.parent / "codex")


@pytest.mark.parametrize("rel", ["ta", "ta/logs", "ta/logs/deeper", "."])
def test_a_workspace_may_not_overlap_the_poll_logs(db, logs, tmp_path, rel):
    """`ta` is the old shared default: a wipe of it would delete the logs."""
    err = agent_install.workspace_conflict(str(tmp_path / rel), "claude", db)
    assert err and "poll logs" in err


@pytest.mark.parametrize("rel", ["other/codex", "other/codex/sub", "other"])
def test_a_workspace_may_not_overlap_another_agents(db, logs, tmp_path, rel):
    _other_agent(db, tmp_path / "other" / "codex")
    err = agent_install.workspace_conflict(str(tmp_path / rel), "claude", db)
    assert err and "codex" in err


def test_an_uninstalled_agents_workspace_still_counts(db, logs, tmp_path):
    """A re-install of that agent would reuse the path."""
    _other_agent(db, tmp_path / "other" / "codex", archived_at="2026-01-01T00:00:00Z")
    assert agent_install.workspace_conflict(str(tmp_path / "other" / "codex"), "claude", db)


def test_an_agent_may_keep_its_own_workspace(db, logs, tmp_path):
    _write(db, ws=str(tmp_path / "ta" / "claude"))
    assert agent_install.workspace_conflict(str(tmp_path / "ta" / "claude"), "claude", db) is None


def test_the_default_layout_has_no_conflicts(db, logs):
    _other_agent(db, agent_install.default_run_path("codex"))
    assert agent_install.workspace_conflict(agent_install.default_run_path("claude"),
                                            "claude", db) is None


def test_a_stored_path_that_would_now_be_refused_pre_fills_the_default(db, logs):
    con = sqlite3.connect(db)
    con.execute("INSERT INTO settings VALUES ('agent_run_path', ?)", (str(logs.parent),))
    con.commit()
    con.close()
    assert agent_install.current_values("claude", db)["AGENT_RUN_PATH"] == \
        agent_install.default_run_path("claude")


def test_the_workspace_question_is_per_agent(db, logs, tmp_path):
    field = agent_install.run_path_field("codex")
    assert field.default == agent_install.default_run_path("codex")
    assert "poll logs" in field.validator(str(logs.parent))
    assert field.validator(field.default) is None
    assert agent_install.RUN_PATH_FIELD.validator is not field.validator


# ── Preconditions ───────────────────────────────────────────────────────────

def _auth(monkeypatch, *, stdout='{"loggedIn": true}', raises=None):
    calls = []

    def run(argv, **kw):
        calls.append(argv)
        if raises:
            raise raises
        return SimpleNamespace(stdout=stdout, stderr="", returncode=0)

    monkeypatch.setattr(agent_install.subprocess, "run", run)
    monkeypatch.setattr(agent_install.shutil, "which", lambda n: f"/usr/local/bin/{n}")
    return calls


def test_preconditions_pass_and_check_the_login_with_the_exact_argv(db, monkeypatch):
    """An unrecognised subcommand is a *prompt* to this CLI — a billed call."""
    calls = _auth(monkeypatch)
    rep = _Rec()
    assert agent_install.check_preconditions(CLAUDE, verify=True, dry_run=False, rep=rep) \
        == "/usr/local/bin/claude"
    assert calls == [["/usr/local/bin/claude", "auth", "status", "--json"]]
    assert "logged in" in rep.text()


def test_no_database_blocks(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_install, "DB_PATH", tmp_path / "missing.db")
    _auth(monkeypatch)
    rep = _Rec()
    assert agent_install.check_preconditions(CLAUDE, verify=True, dry_run=False, rep=rep) is None
    assert "python onboard.py" in rep.text()


def test_a_missing_binary_blocks_without_checking_the_login(db, monkeypatch):
    calls = _auth(monkeypatch)
    monkeypatch.setattr(agent_install.shutil, "which", lambda n: None)
    assert agent_install.check_preconditions(CLAUDE, verify=True, dry_run=False, rep=_Rec()) is None
    assert calls == []


def test_a_logged_out_cli_blocks(db, monkeypatch):
    _auth(monkeypatch, stdout='{"loggedIn": false}')
    rep = _Rec()
    assert agent_install.check_preconditions(CLAUDE, verify=True, dry_run=False, rep=rep) is None
    assert "auth login" in rep.text()


def test_dry_run_downgrades_every_blocker_to_a_warning(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_install, "DB_PATH", tmp_path / "missing.db")
    _auth(monkeypatch, stdout='{"loggedIn": false}')
    rep = _Rec()
    assert agent_install.check_preconditions(CLAUDE, verify=True, dry_run=True, rep=rep)
    assert all(kind == "warn" for kind, _ in rep.msgs)


def test_disable_verification_never_runs_the_cli(db, monkeypatch):
    calls = _auth(monkeypatch, stdout='{"loggedIn": false}')
    assert agent_install.check_preconditions(CLAUDE, verify=False, dry_run=False, rep=_Rec())
    assert calls == []


def test_an_unreachable_login_check_warns_and_continues(db, monkeypatch):
    _auth(monkeypatch, raises=subprocess.TimeoutExpired("claude", 30))
    rep = _Rec()
    assert agent_install.check_preconditions(CLAUDE, verify=True, dry_run=False, rep=rep)
    assert "Could not check" in rep.text()


# ── The model probe ─────────────────────────────────────────────────────────

_REJECTED = "[claude-code:unrecognized_model] ... It may not exist or you may not have access to it."


def _probe(monkeypatch, *, stdout="", stderr="", returncode=0, raises=None):
    calls = []

    def run(argv, **kw):
        calls.append((argv, kw))
        if raises:
            raise raises
        return SimpleNamespace(stdout=stdout, stderr=stderr, returncode=returncode)

    monkeypatch.setattr(agent_install.subprocess, "run", run)
    return agent_install.make_probe(CLAUDE, "/b/claude"), calls


def test_the_probe_argv_is_exact_and_runs_outside_the_repo(monkeypatch):
    probe, calls = _probe(monkeypatch, stdout="ok")
    probe("sonnet")
    argv, kw = calls[0]
    assert argv == ["/b/claude", "-p", "ok", "--output-format", "json", "--model", "sonnet"]
    assert not str(kw["cwd"]).startswith(str(REPO_ROOT))


def test_the_rejection_marker_is_invalid_even_with_exit_0(monkeypatch):
    probe, _ = _probe(monkeypatch, stdout=_REJECTED, returncode=0)
    assert probe("sonnett").status == api_keys.INVALID


def test_the_marker_on_stderr_counts(monkeypatch):
    probe, _ = _probe(monkeypatch, stderr=_REJECTED, returncode=1)
    assert probe("sonnett").status == api_keys.INVALID


def test_a_clean_run_is_valid(monkeypatch):
    probe, _ = _probe(monkeypatch, stdout="ok")
    assert probe("opus").status == api_keys.VALID


def test_a_failed_run_without_the_marker_is_unknown_not_a_verdict(monkeypatch):
    probe, _ = _probe(monkeypatch, stdout="network down", returncode=1)
    assert probe("opus").status == api_keys.UNKNOWN


def test_a_timed_out_probe_is_unknown(monkeypatch):
    probe, _ = _probe(monkeypatch, raises=subprocess.TimeoutExpired("claude", 120))
    assert probe("opus").status == api_keys.UNKNOWN


# ── The fields ──────────────────────────────────────────────────────────────

def test_models_field_offers_the_aliases_first_then_the_catalog():
    field = agent_install.models_field(CLAUDE, ["claude-opus-5", "opus"], None)
    assert field.dynamic_choices({}) == ["opus", "sonnet", "fable", "haiku", "claude-opus-5"]
    assert field.kind == "models"
    assert field.required


def test_every_install_question_has_help_without_ticket_ids():
    import re
    fields = [agent_install.SCOPE_FIELD, agent_install.RUN_PATH_FIELD, agent_install.WIPE_FIELD,
              agent_install.models_field(CLAUDE, [], None)]
    for f in fields:
        assert f.help.strip(), f.key
        assert not re.search(r"\b(TMDEV|VQA|EXQA)-\d+", f.help), f.key


def test_the_models_help_explains_alias_versus_pinned_id():
    help_text = agent_install.models_field(CLAUDE, [], None).help
    assert "alias" in help_text and "full ID" in help_text


# ── Writing the row ─────────────────────────────────────────────────────────

def test_the_first_agent_becomes_the_default_and_replaces_the_legacy_rows(db):
    con = sqlite3.connect(db)
    con.executemany("INSERT INTO settings VALUES (?, ?)", [
        ("agent_binary", "/usr/bin/claude"), ("agent_run_path", "/old"),
        ("install_scope", "user"), ("gemini_api_key", "keep-me")])
    con.commit()
    con.close()
    _write(db, models=("sonnet", "opus"))
    row = _agent(db)
    assert row["is_default"] == 1 and row["weight"] == 1
    assert json.loads(row["models"]) == ["sonnet", "opus"]
    assert row["binary"] == "/usr/local/bin/claude"
    assert row["archived_at"] is None and row["verified_at"]
    assert _settings(db) == {"gemini_api_key": "keep-me"}


def test_a_re_install_keeps_weight_and_default_and_un_archives(db):
    _write(db)
    con = sqlite3.connect(db)
    con.execute("UPDATE agents SET weight = 5, archived_at = '2026-09-01T00:00:00Z'")
    con.commit()
    con.close()
    _write(db, models=("haiku",))
    row = _agent(db)
    assert row["weight"] == 5
    assert row["is_default"] == 1
    assert row["archived_at"] is None
    assert json.loads(row["models"]) == ["haiku"]


def test_an_agent_installed_beside_a_live_default_is_not_made_default(db):
    con = sqlite3.connect(db)
    con.execute(agent_install.AGENTS_SCHEMA)
    con.execute("INSERT INTO agents (id, name, binary, run_path, is_default, created_at, "
                "updated_at) VALUES ('other', 'Other', '/b/other', '/w', 1, 'x', 'x')")
    con.commit()
    con.close()
    _write(db)
    assert _agent(db)["is_default"] == 0


def test_unprobed_models_leave_verified_at_blank(db):
    """--disable-verification must not look like a check that ran."""
    _write(db, verified=False)
    assert _agent(db)["verified_at"] == ""


def test_dry_run_writes_nothing(db):
    _write(db, dry_run=True)
    con = sqlite3.connect(db)
    tables = {n for (n,) in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    assert "agents" not in tables


# ── Deploying ───────────────────────────────────────────────────────────────

def _deploy(db, tmp_path, monkeypatch, adapter=CLAUDE, **values):
    monkeypatch.setattr(agent_install.shutil, "which", lambda n: None)  # no npx on purpose
    ex = Executor(dry_run=True)
    ws = agent_install.deploy(adapter, "/b/" + adapter.name,
                              {"AGENT_RUN_PATH": str(tmp_path / "ws"), **values},
                              ex=ex, rep=NullReporter())
    return ws, [(i.kind, i.detail) for i in ex.intents]


def test_a_user_install_registers_mcp_with_the_agent_being_installed(db, tmp_path, monkeypatch):
    ws, intents = _deploy(db, tmp_path, monkeypatch, INSTALL_SCOPE="user")
    entry = json.dumps({"type": "http", "url": "http://localhost:4100/mcp",
                        "headersHelper": agent_install.mcp_auth().helper})
    runs = [d for k, d in intents if k == "run"]
    # `claude mcp add` refuses an existing name, so the old entry goes first.
    assert runs.index("/b/claude mcp remove --scope user tubematic") < \
        runs.index(f"/b/claude mcp add-json --scope user tubematic {entry}")
    assert ("mkdir", str(agent_install.POLL_LOG_DIR)) in intents
    assert ("mkdir", str(ws / "logs")) not in intents   # logs live beside workspaces
    copied = [d for k, d in intents if k == "copytree"]
    assert any(d.endswith(str(ws / ".claude" / "skills" / "tubematic-operator")) for d in copied)


def test_a_project_install_keeps_everything_in_the_workspace(db, tmp_path, monkeypatch):
    ws, intents = _deploy(db, tmp_path, monkeypatch, INSTALL_SCOPE="project")
    entry = json.dumps({"type": "http", "url": "http://localhost:4100/mcp",
                        "headersHelper": agent_install.mcp_auth().helper})
    assert ("run", f"/b/claude mcp add-json tubematic {entry}") in intents
    assert not any(str(Path.home() / ".claude" / "skills") in d
                   for k, d in intents if k == "copytree")


def test_the_mcp_url_follows_the_stored_port(db, tmp_path, monkeypatch):
    con = sqlite3.connect(db)
    con.execute("INSERT INTO settings VALUES ('mcp_port', '4200')")
    con.commit()
    con.close()
    _, intents = _deploy(db, tmp_path, monkeypatch, INSTALL_SCOPE="user")
    assert any("http://localhost:4200/mcp" in d for k, d in intents if k == "run")


def test_the_allowlist_grants_the_poll_logs_once(tmp_path, monkeypatch):
    """poll.log sits beside the workspace, not in it, and the prompts tell the
    agent to read it — so it is an additional directory. Merged, not
    duplicated, across re-installs."""
    from onboard import actions
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    (tmp_path / "home").mkdir()
    ws = tmp_path / "ws"
    for _ in range(2):
        actions._write_agent_allowlist(ws, ex=Executor(dry_run=False), rep=NullReporter())
    perms = json.loads((ws / ".claude" / "settings.json").read_text())["permissions"]
    assert perms["additionalDirectories"] == [str(actions.POLL_LOG_DIR)]
    assert perms["allow"].count("Read") == 1


def test_the_allowlist_denies_the_data_directory_in_absolute_form(tmp_path, monkeypatch):
    """The data directory holds the database (every API key) and the service
    tokens. Claude Code reads `//path` as absolute and `~/path` as home; a
    single leading slash anchors at the settings file's project instead and
    would deny nothing, which is the mistake this pins."""
    from onboard import actions
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setattr(actions, "DATA_ROOT", home / ".tubematic-data")
    ws = tmp_path / "ws"
    for _ in range(2):
        actions._write_agent_allowlist(ws, ex=Executor(dry_run=False), rep=NullReporter())
    deny = json.loads((ws / ".claude" / "settings.json").read_text())["permissions"]["deny"]
    assert deny == [f"Read(/{home}/.tubematic-data/**)", "Read(~/.tubematic-data/**)"]
    assert deny[0].startswith("Read(//")
    # The poll logs the prompts point the agent at are not under it.
    assert not any(str(actions.POLL_LOG_DIR).startswith(r[len("Read(/"):-len("/**)")])
                   for r in deny if r.startswith("Read(//"))


def test_the_data_directory_deny_keeps_the_operators_own_denies(tmp_path, monkeypatch):
    from onboard import actions
    monkeypatch.setenv("HOME", str(tmp_path))
    ws = tmp_path / "ws"
    (ws / ".claude").mkdir(parents=True)
    (ws / ".claude" / "settings.json").write_text(json.dumps(
        {"permissions": {"deny": ["Bash(rm *)"]}}))
    actions._write_agent_allowlist(ws, ex=Executor(dry_run=False), rep=NullReporter())
    deny = json.loads((ws / ".claude" / "settings.json").read_text())["permissions"]["deny"]
    assert deny[0] == "Bash(rm *)"
    assert set(actions.claude_read_denies()) <= set(deny)


def test_the_claude_checklist_fails_without_the_data_directory_deny(tmp_path, monkeypatch):
    from onboard import actions
    monkeypatch.setenv("HOME", str(tmp_path))
    ws = tmp_path / "ws"
    actions._write_agent_allowlist(ws, ex=Executor(dry_run=False), rep=NullReporter())
    row = {"id": "claude", "binary": "/b/claude", "run_path": str(ws),
           "install_scope": "user", "models": ["opus"]}
    check = next(c for label, c in _checks(row, monkeypatch, tmp_path).items()
                 if "data directory denied" in label)
    assert check.ok is True
    settings = ws / ".claude" / "settings.json"
    data = json.loads(settings.read_text())
    data["permissions"]["deny"] = []
    settings.write_text(json.dumps(data))
    check = next(c for label, c in _checks(row, monkeypatch, tmp_path).items()
                 if "data directory denied" in label)
    assert check.ok is False


def test_wipe_deletes_an_existing_workspace_first(db, tmp_path, monkeypatch):
    (tmp_path / "ws").mkdir()
    ws, intents = _deploy(db, tmp_path, monkeypatch, INSTALL_SCOPE="user",
                          WIPE_AGENT_WORKSPACE="true")
    assert intents[0] == ("rmtree", str(ws))


# ── The whole flow ──────────────────────────────────────────────────────────

def test_a_blocked_precondition_asks_nothing(monkeypatch):
    monkeypatch.setattr(agent_install, "check_preconditions", lambda *a, **k: None)
    monkeypatch.setattr("onboard.prompt.prompt_fields",
                        lambda *a, **k: pytest.fail("must not prompt"))
    assert agent_install.run_install_agent("claude") == 1


def test_a_dry_run_never_probes_and_records_unverified(monkeypatch):
    """A probe for a valid model is a real run, so a dry run must not make one."""
    seen = {}
    monkeypatch.setattr(agent_install, "check_preconditions", lambda *a, **k: "/b/claude")
    monkeypatch.setattr(CLAUDE, "suggest_models", classmethod(lambda cls, b: []))

    def fake_prompt(fields, cfg, *, opts, before_field=None):
        seen["verify_keys"] = opts.verify_keys
        cfg.values["AGENT_MODELS"] = '["opus"]'

    monkeypatch.setattr("onboard.prompt.prompt_fields", fake_prompt)
    monkeypatch.setattr(agent_install, "deploy", lambda *a, **k: Path("/srv/ws"))
    monkeypatch.setattr(agent_install, "write_agent_row",
                        lambda *a, **k: seen.update(models=a[4], verified=k["verified"]))
    monkeypatch.setattr("onboard.plain.print_verify", lambda: None)
    assert agent_install.run_install_agent("claude", dry_run=True) == 0
    assert seen == {"verify_keys": False, "models": ["opus"], "verified": False}


# ── Effort level (TMDEV-106) ────────────────────────────────────────────────

def _flow(monkeypatch, *, full=False, answers=None, verify=True, probe=None):
    """Drive run_install_agent with every subprocess and write stubbed out,
    returning (fields it asked for, kwargs write_agent_row received)."""
    seen = {}
    monkeypatch.setattr(agent_install, "check_preconditions", lambda *a, **k: "/b/claude")
    monkeypatch.setattr(CLAUDE, "suggest_models", classmethod(lambda cls, b: []))
    monkeypatch.setattr(agent_install, "probe_effort",
                        probe or (lambda adapter, binary, effort, model='': None))

    def fake_prompt(fields, cfg, *, opts, before_field=None):
        seen["asked"] = [f.key for f in fields]
        cfg.values["AGENT_MODELS"] = '["opus"]'
        cfg.values.update(answers or {})

    monkeypatch.setattr("onboard.prompt.prompt_fields", fake_prompt)
    monkeypatch.setattr(agent_install, "deploy", lambda *a, **k: Path("/srv/ws"))
    monkeypatch.setattr(agent_install, "write_agent_row",
                        lambda adapter, binary, values, ws, models, **k:
                            seen.update(values=dict(values)))
    monkeypatch.setattr("onboard.plain.print_verify", lambda: None)
    assert agent_install.run_install_agent("claude", verify_keys=verify,
                                           full_questionnaire=full) == 0
    return seen


def test_the_minimal_questionnaire_never_asks_for_an_effort(monkeypatch):
    """Rule 2 from the ticket. --install-agent builds its own field list, so
    the `advanced` attribute only works here because the flow filters on it."""
    seen = _flow(monkeypatch)
    assert "AGENT_EFFORT" not in seen["asked"]


def test_a_skipped_effort_question_still_stores_high(monkeypatch):
    """Rule 1: an install that never touches the setting runs at high."""
    seen = _flow(monkeypatch)
    assert seen["values"]["AGENT_EFFORT"] == "high"


def test_the_full_questionnaire_asks_for_it(monkeypatch):
    seen = _flow(monkeypatch, full=True)
    assert "AGENT_EFFORT" in seen["asked"]


def test_an_answered_effort_reaches_the_row(monkeypatch):
    seen = _flow(monkeypatch, full=True, answers={"AGENT_EFFORT": "max"})
    assert seen["values"]["AGENT_EFFORT"] == "max"


def test_the_effort_field_offers_exactly_the_cli_levels():
    field = agent_install.effort_field(CLAUDE)
    assert field.choices == list(CLAUDE.EFFORTS)
    assert field.advanced is True


def test_the_stored_default_is_the_fields_own_default_not_a_copy(db, monkeypatch):
    """The TMDEV-74 trap: a skipped question equals answering it with its
    default only while both copies of that default agree. There must not be
    two copies — so moving the field's default must move what a skipped
    install stores, and this test fails if someone re-hardcodes the literal.
    """
    monkeypatch.setattr(agent_install, "effort_field",
                        lambda adapter: agent_install.Field(
                            "AGENT_EFFORT", "Effort", kind="select",
                            choices=list(adapter.EFFORTS), default="xhigh", advanced=True))
    _write(db)
    assert _agent(db)["effort"] == "xhigh"


def test_a_written_row_carries_the_effort(db):
    agent_install.write_agent_row(
        CLAUDE, "/b/claude", {"INSTALL_SCOPE": "user", "AGENT_EFFORT": "low"},
        Path("/srv/ws"), ["opus"], verified=True, ex=Executor(dry_run=False))
    assert _agent(db)["effort"] == "low"


def test_a_re_install_prefills_the_stored_effort(db):
    agent_install.write_agent_row(
        CLAUDE, "/b/claude", {"INSTALL_SCOPE": "user", "AGENT_EFFORT": "max"},
        Path("/srv/ws"), ["opus"], verified=True, ex=Executor(dry_run=False))
    assert agent_install.current_values("claude", db)["AGENT_EFFORT"] == "max"


# ── The install-time --effort probe ──

def _run(stderr="", returncode=0):
    return SimpleNamespace(stdout="", stderr=stderr, returncode=returncode)


def test_the_probe_warns_when_the_cli_does_not_know_the_flag(monkeypatch):
    monkeypatch.setattr(subprocess, "run",
                        lambda *a, **k: _run("error: unknown option '--effort'\n", 1))
    msg = agent_install.probe_effort(CLAUDE, "/b/claude", "high")
    assert msg and "--effort" in msg and "'high'" in msg


def test_the_probe_is_silent_on_a_clean_run(monkeypatch):
    monkeypatch.setattr(subprocess, "run", lambda *a, **k: _run())
    assert agent_install.probe_effort(CLAUDE, "/b/claude", "high") is None


@pytest.mark.parametrize("failure", [
    OSError("boom"), subprocess.TimeoutExpired("claude", 1)])
def test_the_probe_stays_silent_on_a_transport_failure(monkeypatch, failure):
    """A blip is not evidence about the flag, and warning on one would cry
    wolf on every flaky install."""
    def boom(*a, **k):
        raise failure
    monkeypatch.setattr(subprocess, "run", boom)
    assert agent_install.probe_effort(CLAUDE, "/b/claude", "high") is None


def test_the_probe_argv_carries_the_effort_and_no_model(monkeypatch):
    seen = {}
    def _capture(argv, **k):
        seen["argv"] = argv
        return _run()

    monkeypatch.setattr(subprocess, "run", _capture)
    agent_install.probe_effort(CLAUDE, "/b/claude", "max")
    assert seen["argv"] == ["/b/claude", "-p", "ok", "--output-format", "json", "--effort", "max"]


def test_the_probe_runs_even_when_the_question_was_skipped(monkeypatch):
    """The default install is the one that never asks, and is also the common
    one — so it is exactly the install that must still be checked."""
    seen = {}
    def _probe(adapter, binary, effort, model=""):
        seen["effort"] = effort
        seen["model"] = model
        return None

    _flow(monkeypatch, probe=_probe)
    assert seen["effort"] == "high"
    # ...and with the default model, so a pair-level rejection is reachable.
    assert seen["model"] == "opus"


def test_a_dry_run_and_disable_verification_never_probe(monkeypatch):
    """A probe is a real (tiny) billed run, like the model probes."""
    def fail(*a, **k):
        pytest.fail("must not probe")
    _flow(monkeypatch, verify=False, probe=fail)


def test_an_unsupported_flag_warns_but_still_installs(monkeypatch):
    """poll.py drops the flag at runtime, so a warned install still works —
    blocking here would refuse an install that is merely degraded."""
    seen = _flow(monkeypatch, probe=lambda *a: "CLI does not accept --effort")
    assert seen["values"]["AGENT_EFFORT"] == "high"


# ── Uninstalling ────────────────────────────────────────────────────────────

SHIPPED_SKILLS = sorted(d.name for d in (agent_install.REPO_ROOT / "agent_files" / "skills")
                        .iterdir() if d.is_dir())
SHIPPED_COMMANDS = sorted(f.name for f in (agent_install.REPO_ROOT / "agent_files" / "claude"
                                           / "commands").glob("*.md"))


@pytest.fixture
def installed(db, tmp_path, monkeypatch):
    """A user-scope install laid out on disk, next to files that are not ours."""
    home, ws = tmp_path / "home", tmp_path / "ws"
    monkeypatch.setenv("HOME", str(home))
    for skills in (home / ".claude" / "skills", ws / ".claude" / "skills"):
        for s in SHIPPED_SKILLS + ["someone-elses-skill"]:
            (skills / s).mkdir(parents=True)
            (skills / s / "SKILL.md").write_text("x")
    (home / ".claude" / "commands").mkdir(parents=True)
    for c in SHIPPED_COMMANDS + ["mine.md"]:
        (home / ".claude" / "commands" / c).write_text("x")
    (ws / "notes.md").write_text("keep me")   # the agent's own working file
    _write(db, ws=str(ws))

    runs = []

    def fake_run(cmd, cwd=None, **kw):
        runs.append((list(cmd), cwd))
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("onboard.executor.subprocess.run", fake_run)
    monkeypatch.setattr(agent_install.shutil, "which",
                        lambda n: "/b/claude" if n in ("claude", "/usr/local/bin/claude") else None)
    monkeypatch.setattr(agent_install, "_ensure_db_writable", lambda ex, rep: True)
    return SimpleNamespace(home=home, ws=ws, runs=runs)


def _left(root):
    return sorted(p.name for p in root.iterdir())


def test_uninstall_removes_only_what_the_install_deployed(installed, db):
    assert agent_install.run_uninstall_agent("claude", confirm=lambda m: True) == 0
    assert _left(installed.home / ".claude" / "skills") == ["someone-elses-skill"]
    assert _left(installed.ws / ".claude" / "skills") == ["someone-elses-skill"]
    assert _left(installed.home / ".claude" / "commands") == ["mine.md"]
    assert (installed.ws / "notes.md").read_text() == "keep me"
    assert installed.runs == [(["/b/claude", "mcp", "remove", "--scope", "user", "tubematic"],
                               agent_install.REPO_ROOT)]


def test_uninstall_archives_the_row_rather_than_deleting_it(installed, db):
    agent_install.run_uninstall_agent("claude", confirm=lambda m: True)
    row = _agent(db)
    assert row is not None and row["archived_at"] and row["is_default"] == 0
    assert json.loads(row["models"]) == ["opus"]


def test_a_re_install_after_uninstall_restores_the_row(installed, db):
    agent_install.run_uninstall_agent("claude", confirm=lambda m: True)
    _write(db, ws=str(installed.ws))
    row = _agent(db)
    assert row["archived_at"] is None and row["is_default"] == 1


def test_declining_changes_nothing(installed, db):
    assert agent_install.run_uninstall_agent("claude", confirm=lambda m: False) == 1
    assert len(_left(installed.home / ".claude" / "skills")) == len(SHIPPED_SKILLS) + 1
    assert installed.runs == [] and _agent(db)["archived_at"] is None


def test_a_dry_run_asks_nothing_and_changes_nothing(installed, db):
    rc = agent_install.run_uninstall_agent(
        "claude", dry_run=True, confirm=lambda m: pytest.fail("must not ask"))
    assert rc == 0
    assert len(_left(installed.home / ".claude" / "commands")) == len(SHIPPED_COMMANDS) + 1
    assert installed.runs == [] and _agent(db)["archived_at"] is None


def test_uninstalling_an_agent_that_is_not_installed_fails(db):
    assert agent_install.run_uninstall_agent(
        "claude", confirm=lambda m: pytest.fail("must not ask")) == 1


def test_uninstalling_twice_is_a_no_op(installed, db):
    agent_install.run_uninstall_agent("claude", confirm=lambda m: True)
    first = _agent(db)["archived_at"]
    assert agent_install.run_uninstall_agent(
        "claude", confirm=lambda m: pytest.fail("must not ask")) == 0
    assert _agent(db)["archived_at"] == first


def test_the_default_cannot_be_uninstalled_while_another_agent_is_live(installed, db):
    con = sqlite3.connect(db)
    con.execute("INSERT INTO agents (id, name, binary, run_path, is_default, created_at, "
                "updated_at) VALUES ('other', 'Other', '/b/other', '/w', 0, 'x', 'x')")
    con.commit()
    con.close()
    assert agent_install.run_uninstall_agent(
        "claude", confirm=lambda m: pytest.fail("must not ask")) == 1
    assert _agent(db)["archived_at"] is None and installed.runs == []


def test_a_project_install_is_uninstalled_from_its_workspace(db, tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    (ws / ".claude" / "skills" / SHIPPED_SKILLS[0]).mkdir(parents=True)
    (ws / ".claude" / "commands").mkdir()
    (ws / ".claude" / "commands" / SHIPPED_COMMANDS[0]).write_text("x")
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    row = {"run_path": str(ws), "install_scope": "project"}
    assert agent_install.deployed_paths(CLAUDE, row) == [
        ws / ".claude" / "skills" / SHIPPED_SKILLS[0],
        ws / ".claude" / "commands" / SHIPPED_COMMANDS[0]]
    assert CLAUDE.mcp_remove_argv("/b/claude", "project") == \
        ["/b/claude", "mcp", "remove", "tubematic"]


# ── Listing ─────────────────────────────────────────────────────────────────

def test_list_agents_shows_supported_and_installed(db, capsys):
    _write(db, models=("sonnet", "opus"))
    con = sqlite3.connect(db)
    con.execute("INSERT INTO agents (id, name, binary, run_path, models, archived_at, "
                "created_at, updated_at) VALUES ('old', 'Old', '/b/old', '/w', '[\"m\"]', "
                "'2026-01-01T00:00:00Z', 'y', 'y')")
    con.commit()
    con.close()
    agent_install.print_agents()
    out = capsys.readouterr().out
    assert "Supported agents" in out and "Claude Code" in out
    assert "default agent" in out and "sonnet (default), opus" in out
    assert "uninstalled" in out


def test_list_agents_with_none_installed_says_how_to_install(db, capsys):
    agent_install.print_agents()
    assert "--install-agent <agent>" in capsys.readouterr().out


# ── Deploying Codex ─────────────────────────────────────────────────────────

def test_a_codex_install_uses_codex_paths_and_argv(db, tmp_path, monkeypatch):
    ws, intents = _deploy(db, tmp_path, monkeypatch, CODEX, INSTALL_SCOPE="user")
    assert ("run", "/b/codex mcp add tubematic --url http://localhost:4100/mcp") in intents
    copied = [d for k, d in intents if k == "copytree"]
    assert any(d.endswith(str(Path.home() / ".codex" / "skills" / "tubematic-operator"))
               for d in copied)
    assert ("mkdir", str(agent_install.POLL_LOG_DIR)) in intents


def test_a_codex_install_touches_nothing_claude_owns(db, tmp_path, monkeypatch):
    """The regression that would be invisible otherwise: installing Codex must
    not create a .claude directory, a settings.json allowlist or a trust record."""
    _, intents = _deploy(db, tmp_path, monkeypatch, CODEX, INSTALL_SCOPE="user")
    assert not any(".claude" in d for _, d in intents)


def test_codex_deploys_no_commands_and_no_second_skills_copy(db, tmp_path, monkeypatch):
    ws, intents = _deploy(db, tmp_path, monkeypatch, CODEX, INSTALL_SCOPE="user")
    assert not any(d.endswith(".md") for k, d in intents if k == "copy_file")
    assert not any(str(ws) in d for k, d in intents if k == "copytree")


def test_codex_passes_its_own_flag_to_the_remotion_installer(db, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(agent_install, "_install_remotion_skills",
                        lambda cwd, flag, **kw: calls.append(flag) or True)
    _deploy(db, tmp_path, monkeypatch, CODEX, INSTALL_SCOPE="user")
    assert calls == ["codex"]


def test_claude_still_passes_the_claude_code_flag(db, tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(agent_install, "_install_remotion_skills",
                        lambda cwd, flag, **kw: calls.append(flag) or True)
    _deploy(db, tmp_path, monkeypatch, CLAUDE, INSTALL_SCOPE="user")
    assert calls == ["claude-code"]


# ── Per-agent questions ─────────────────────────────────────────────────────

def test_the_scope_question_is_only_asked_when_there_is_a_choice(db):
    assert agent_install.scope_field(CLAUDE).choices == ["user", "project"]
    fields = agent_install.install_fields(CODEX, [], lambda m: None)
    assert not any(f.key == "INSTALL_SCOPE" for f in fields)
    fields = agent_install.install_fields(CLAUDE, [], lambda m: None)
    assert fields[0].key == "INSTALL_SCOPE"


def test_codex_pre_fills_the_only_scope_it_supports(db):
    assert agent_install.current_values("codex", db)["INSTALL_SCOPE"] == "user"


def test_a_stored_scope_the_agent_cannot_honour_is_clamped(db):
    """A legacy `install_scope=project` settings row, or a hand-edited agents
    row, must not hand Codex a scope its deploy cannot honour."""
    con = sqlite3.connect(db)
    con.execute("INSERT INTO settings VALUES ('install_scope', 'project')")
    con.commit()
    con.close()
    assert agent_install.current_values("codex", db)["INSTALL_SCOPE"] == "user"
    assert agent_install.current_values("claude", db)["INSTALL_SCOPE"] == "project"


def test_the_effort_probe_is_skipped_for_an_agent_that_cannot_reject_the_flag(monkeypatch):
    """A real (billed) run that could never produce a verdict is waste, not
    caution: Codex's rejection depends on the model/effort PAIR, so a probe
    with no model could never produce a verdict."""
    monkeypatch.setattr(agent_install.subprocess, "run",
                        lambda *a, **k: pytest.fail("no probe should run"))
    assert agent_install.probe_effort(CODEX, "/b/codex", "high") is None


def test_codex_does_probe_the_effort_once_a_model_is_known(monkeypatch):
    """With the default model it becomes a real check, and it is the only place
    an incompatible model/effort pair is caught in front of a human."""
    monkeypatch.setattr(
        agent_install.subprocess, "run",
        lambda *a, **k: SimpleNamespace(
            stdout="", returncode=1,
            stderr='"param": "reasoning.effort", Unsupported value: \'max\' is not supported '
                   "with the 'gpt-5.5' model."))
    msg = agent_install.probe_effort(CODEX, "/b/codex", "max", "gpt-5.5")
    assert msg and "max" in msg and "gpt-5.5" in msg


# ── Uninstalling ────────────────────────────────────────────────────────────

def test_uninstalling_codex_lists_only_its_user_scope_skills(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_install.Path, "home", staticmethod(lambda: tmp_path))
    skills = tmp_path / ".codex" / "skills"
    (skills / "tubematic-operator").mkdir(parents=True)
    row = {"id": "codex", "run_path": str(tmp_path / "ws"), "install_scope": "user"}
    assert agent_install.deployed_paths(CODEX, row) == [skills / "tubematic-operator"]


def test_uninstalling_codex_uses_codexs_own_remove_argv():
    assert CODEX.mcp_remove_argv("/b/codex", "user") == ["/b/codex", "mcp", "remove", "tubematic"]


def test_uninstalling_claude_still_sweeps_commands_and_the_workspace_copy(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_install.Path, "home", staticmethod(lambda: tmp_path))
    ws = tmp_path / "ws"
    (tmp_path / ".claude" / "skills" / "tubematic-operator").mkdir(parents=True)
    (ws / ".claude" / "skills" / "tubematic-operator").mkdir(parents=True)
    (tmp_path / ".claude" / "commands").mkdir(parents=True)
    (tmp_path / ".claude" / "commands" / "tubematic.md").write_text("x")
    row = {"id": "claude", "run_path": str(ws), "install_scope": "user"}
    paths = agent_install.deployed_paths(CLAUDE, row)
    assert tmp_path / ".claude" / "commands" / "tubematic.md" in paths
    assert ws / ".claude" / "skills" / "tubematic-operator" in paths


# ── Post-install verification ───────────────────────────────────────────────
# The checklist used to read Claude's layout for every agent, so a correct Codex
# install reported skills that were never there and warned, on every run, about
# commands, an allowlist and a trust record Codex deliberately does not have.

def _checks(agent, monkeypatch, home):
    from onboard import checks
    monkeypatch.setattr(checks.Path, "home", staticmethod(lambda: home))
    monkeypatch.setattr(checks.shutil, "which", lambda n: "/b/" + str(n))
    monkeypatch.setattr(checks, "_mcp_registered_user", lambda b="": True)
    return {c.label: c for c in checks._agent_checks(agent)}


def _codex_row(home):
    return {"id": "codex", "binary": "/b/codex", "run_path": str(home / "ws"),
            "install_scope": "user", "models": ["gpt-5.6-sol"]}


def test_a_correct_codex_install_verifies_clean(tmp_path, monkeypatch):
    (tmp_path / ".codex" / "skills" / "tubematic-operator").mkdir(parents=True)
    (tmp_path / ".agents" / "skills" / "remotion-best-practices").mkdir(parents=True)
    (tmp_path / ".agents" / "skills" / "remotion-best-practices" / "SKILL.md").write_text("x")
    (tmp_path / "ws").mkdir()
    monkeypatch.setattr(agent_install, "POLL_LOG_DIR", tmp_path / "logs")
    (tmp_path / "logs").mkdir()
    from onboard import checks
    monkeypatch.setattr(checks, "POLL_LOG_DIR", tmp_path / "logs")
    monkeypatch.delenv("CODEX_HOME", raising=False)
    _codex_toml(tmp_path, agent_install.mcp_auth().helper)
    items = _checks(_codex_row(tmp_path), monkeypatch, tmp_path)
    failed = [label for label, c in items.items() if not c.ok]
    assert failed == [], failed


def _codex_toml(home, helper=None):
    body = '[mcp_servers.tubematic]\nurl = "http://localhost:4100/mcp"\n'
    if helper:
        body += f"http_headers_helper = {json.dumps(helper)}\n"
    (home / ".codex").mkdir(exist_ok=True)
    (home / ".codex" / "config.toml").write_text(body)


def _auth_check(items):
    return next(c for label, c in items.items() if "MCP token wired" in label)


@pytest.mark.parametrize("helper", [None, "/old/install/.venv/bin/python3 /old/x.py"])
def test_a_codex_registration_without_this_installs_helper_is_reported(tmp_path, monkeypatch,
                                                                      helper):
    """Missing, or pointing at a moved install: either way every MCP call is a 401."""
    monkeypatch.delenv("CODEX_HOME", raising=False)
    _codex_toml(tmp_path, helper)
    check = _auth_check(_checks(_codex_row(tmp_path), monkeypatch, tmp_path))
    assert check.ok is False
    assert "401" in check.hint


def test_a_claude_registration_is_checked_for_its_header_helper(tmp_path, monkeypatch):
    row = {"id": "claude", "binary": "/b/claude", "run_path": str(tmp_path / "ws"),
           "install_scope": "user", "models": ["opus"]}
    entry = {"type": "http", "url": "u"}
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"tubematic": entry}}))
    assert _auth_check(_checks(row, monkeypatch, tmp_path)).ok is False
    entry["headersHelper"] = agent_install.mcp_auth().helper
    (tmp_path / ".claude.json").write_text(json.dumps({"mcpServers": {"tubematic": entry}}))
    assert _auth_check(_checks(row, monkeypatch, tmp_path)).ok is True


def test_a_claude_project_registration_is_read_from_its_workspace(tmp_path, monkeypatch):
    ws = tmp_path / "ws"
    row = {"id": "claude", "binary": "/b/claude", "run_path": str(ws),
           "install_scope": "project", "models": ["opus"]}
    entry = {"type": "http", "url": "u", "headersHelper": agent_install.mcp_auth().helper}
    (tmp_path / ".claude.json").write_text(json.dumps(
        {"projects": {str(ws): {"mcpServers": {"tubematic": entry}}}}))
    assert _auth_check(_checks(row, monkeypatch, tmp_path)).ok is True


def test_codex_is_not_asked_for_claude_only_artefacts(tmp_path, monkeypatch):
    items = _checks(_codex_row(tmp_path), monkeypatch, tmp_path)
    labels = " ".join(items)
    assert "commands" not in labels
    assert "allowlist" not in labels
    assert "trusted" not in labels
    assert ".claude" not in labels


def test_the_skills_check_needs_a_real_skill_not_just_the_directory(tmp_path, monkeypatch):
    """The old check tested only that the directory existed, which the Remotion
    installer also creates — so an agent whose own skills never landed still
    reported installed."""
    (tmp_path / ".codex" / "skills").mkdir(parents=True)
    items = _checks(_codex_row(tmp_path), monkeypatch, tmp_path)
    skills = next(c for label, c in items.items() if "user skills installed" in label)
    assert skills.ok is False


def test_claude_still_gets_its_own_four_checks(tmp_path, monkeypatch):
    row = {"id": "claude", "binary": "/b/claude", "run_path": str(tmp_path / "ws"),
           "install_scope": "user", "models": ["opus"]}
    labels = " ".join(_checks(row, monkeypatch, tmp_path))
    assert ".claude/commands" in labels
    assert "allowlist" in labels
    assert "trusted" in labels


def test_the_models_help_only_explains_aliases_to_an_agent_that_has_them():
    """Codex's models are catalog slugs; telling a Codex user about `opus` and
    a `claude-opus-5`-shaped ID describes names their CLI would reject."""
    claude_help = agent_install.models_field(CLAUDE, [], lambda m: None).help
    codex_help = agent_install.models_field(CODEX, [], lambda m: None).help
    assert "alias" in claude_help and "opus" in claude_help
    assert "alias" not in codex_help
    assert "opus" not in codex_help and "claude" not in codex_help
    # The part that is true for both must survive in both.
    for text in (claude_help, codex_help):
        assert "The first is this agent's default" in text
        assert "checked against the installed CLI" in text


def test_a_non_default_config_root_blocks_the_install(db, monkeypatch, tmp_path):
    """Cron strips the environment, so a root chosen by environment variable
    reaches the install and never the scheduled runs — and that root holds both
    the agent's authentication and the skills this installer deploys. Blocked
    for the same reason a logged-out CLI is: an install known to produce a
    silently broken schedule is not worth completing."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setattr(agent_install.shutil, "which", lambda n: "/b/codex")
    monkeypatch.setattr(agent_install.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="", stderr="Logged in using ChatGPT",
                                                        returncode=0))
    rep = _Rec()
    assert agent_install.check_preconditions(CODEX, verify=True, dry_run=False, rep=rep) is None
    assert "config root" in rep.text()
    assert "cron does not pass that environment on" in rep.text()


def test_a_non_default_config_root_only_warns_under_dry_run(db, monkeypatch, tmp_path):
    """A dry run exists to preview the questions on a machine that is not ready."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setattr(agent_install.shutil, "which", lambda n: "/b/codex")
    rep = _Rec()
    assert agent_install.check_preconditions(
        CODEX, verify=False, dry_run=True, rep=rep) is not None


def test_the_default_config_root_says_nothing(db, monkeypatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.setattr(agent_install.shutil, "which", lambda n: "/b/codex")
    monkeypatch.setattr(agent_install.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout="", stderr="Logged in using ChatGPT",
                                                        returncode=0))
    rep = _Rec()
    agent_install.check_preconditions(CODEX, verify=True, dry_run=False, rep=rep)
    assert "config root" not in rep.text()


def test_a_config_root_set_after_install_blocks_uninstall(db, monkeypatch, tmp_path):
    """The dangerous case is not installing under an override — install already
    refuses that — but setting one afterwards. Uninstall would then archive the
    row while removing nothing, leaving the real skills and MCP registration in
    place and the agent looking uninstalled."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "elsewhere"))
    rep = _Rec()
    monkeypatch.setattr(agent_install, "PlainReporter", lambda **k: rep, raising=False)
    assert agent_install.config_root_conflict(CODEX) is not None
    assert agent_install.config_root_conflict(CLAUDE) is None


def test_the_guard_is_quiet_on_the_default_root(monkeypatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert agent_install.config_root_conflict(CODEX) is None


def test_upgrade_refuses_to_redeploy_into_the_wrong_root(db, monkeypatch, tmp_path):
    """A redeploy there would put skills in a root the scheduled runs never
    read, and report success."""
    import upgrade
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "elsewhere"))
    con = sqlite3.connect(db)
    con.execute(agent_install.AGENTS_SCHEMA)
    con.execute("INSERT INTO agents (id, name, binary, run_path, created_at, updated_at) "
                "VALUES ('codex', 'Codex', '/b/codex', ?, 'x', 'x')", (str(tmp_path / "ws"),))
    con.commit(); con.close()
    rep = _Rec()
    deployed = []
    monkeypatch.setattr(agent_install, "deploy", lambda *a, **k: deployed.append(a))
    upgrade._redeploy_agents(Executor(dry_run=True), rep, db_path=db)
    assert deployed == []
    assert "not redeployed" in rep.text()


def test_the_diagnostics_describe_the_root_cron_will_use(tmp_path, monkeypatch):
    """Cron never inherits an environment override, so a read-only check that
    resolved one would report a perfectly good install as missing its skills
    and send the user to re-run an install that was already correct."""
    (tmp_path / ".codex" / "skills" / "tubematic-operator").mkdir(parents=True)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "elsewhere"))
    items = _checks(_codex_row(tmp_path), monkeypatch, tmp_path)
    skills = next(c for label, c in items.items() if "user skills installed" in label)
    assert skills.ok is True, "resolved the override instead of the root cron uses"
    assert any("config root" in label for label in items), "the disagreement must be reported"


def test_the_diagnostics_say_nothing_about_the_root_when_it_matches(tmp_path, monkeypatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    (tmp_path / ".codex" / "skills" / "tubematic-operator").mkdir(parents=True)
    items = _checks(_codex_row(tmp_path), monkeypatch, tmp_path)
    assert not any("config root" in label for label in items)


def test_a_dry_run_uninstall_still_surfaces_the_conflict(db, monkeypatch, tmp_path, capsys):
    """Previewing is a dry run's job, but a silent one previews a root the real
    run would never touch."""
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "elsewhere"))
    con = sqlite3.connect(db)
    con.execute(agent_install.AGENTS_SCHEMA)
    con.execute("INSERT INTO agents (id, name, binary, run_path, created_at, updated_at) "
                "VALUES ('codex', 'Codex', '/b/codex', ?, 'x', 'x')", (str(tmp_path / "ws"),))
    con.commit(); con.close()
    rc = agent_install.run_uninstall_agent("codex", dry_run=True, confirm=lambda m: False)
    out = capsys.readouterr().out
    assert "config root" in out
    assert rc != 1 or "config root" in out


# ── Deploying OpenCode ──────────────────────────────────────────────────────
# OpenCode is the first agent whose permissions live in a config document of
# its own rather than in Claude's settings.json, and the first with no
# deregistration command at all.

@pytest.fixture
def opencode_home(tmp_path, monkeypatch):
    """A private HOME with no XDG override, so the roots are deterministic."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(agent_install.Path, "home", staticmethod(lambda: tmp_path))
    from onboard import actions
    monkeypatch.setattr(actions.Path, "home", staticmethod(lambda: tmp_path))
    return tmp_path


def test_an_opencode_user_install_uses_its_own_roots_and_argv(db, tmp_path, monkeypatch,
                                                              opencode_home):
    ws, intents = _deploy(db, tmp_path, monkeypatch, OPENCODE, INSTALL_SCOPE="user")
    cfg = opencode_home / ".config" / "opencode"
    header = f"Authorization=Bearer {{file:{agent_install.mcp_auth().token_file}}}"
    assert ("run", "/b/opencode mcp add tubematic --global --url "
                   f"http://localhost:4100/mcp --header {header}") in intents
    copied = [d for k, d in intents if k == "copytree"]
    assert any(d.endswith(str(cfg / "skills" / "tubematic-operator")) for d in copied)
    # Commands: OpenCode has them, unlike Codex.
    assert any(f"-> {cfg / 'commands'}/" in d for k, d in intents if k == "copy_file")


def test_an_opencode_project_install_registers_without_global(db, tmp_path, monkeypatch,
                                                              opencode_home):
    ws, intents = _deploy(db, tmp_path, monkeypatch, OPENCODE, INSTALL_SCOPE="project")
    header = f"Authorization=Bearer {{file:{agent_install.mcp_auth().token_file}}}"
    assert ("run", f"/b/opencode mcp add tubematic --url http://localhost:4100/mcp "
                   f"--header {header}") in intents
    assert any(d.endswith(str(ws / ".opencode" / "skills" / "tubematic-operator"))
               for k, d in intents if k == "copytree")


def test_an_opencode_install_touches_nothing_claude_owns(db, tmp_path, monkeypatch,
                                                         opencode_home):
    _, intents = _deploy(db, tmp_path, monkeypatch, OPENCODE, INSTALL_SCOPE="user")
    assert not any(".claude" in d for _, d in intents)


def test_an_opencode_install_writes_only_into_its_own_document(
        db, tmp_path, monkeypatch, opencode_home):
    """Workspace-scoped at BOTH scopes, like Claude's allowlist: cron runs the
    agent from there, and a user-scope install must not reach into the
    operator's own agent config to restrict it.

    `.opencode/opencode.json`, not the workspace's direct `opencode.json`, and
    that is a correctness requirement — measured, the direct file is
    overridden by an ancestor `~/.opencode/opencode.json`, while this one
    outranks every other document."""
    for scope in ("user", "project"):
        ws, intents = _deploy(db, tmp_path, monkeypatch, OPENCODE, INSTALL_SCOPE=scope)
        written = [d for k, d in intents if k == "write_file"]
        assert str(ws / ".opencode" / "opencode.json") in written, scope
        # Nothing the operator owns is written — not the global config, not the
        # workspace's direct file.
        assert str(ws / "opencode.json") not in written, scope
        assert not any(str(opencode_home / ".config") in d for d in written), scope


def test_opencode_passes_its_own_flag_to_the_remotion_installer(db, tmp_path, monkeypatch,
                                                                opencode_home):
    calls = []
    monkeypatch.setattr(agent_install, "_install_remotion_skills",
                        lambda cwd, flag, **kw: calls.append(flag) or True)
    _deploy(db, tmp_path, monkeypatch, OPENCODE, INSTALL_SCOPE="user")
    assert calls == ["opencode"]


def test_opencode_is_asked_the_scope_question():
    """Unlike Codex, both of OpenCode's scopes are real, so the question is
    asked rather than seeded."""
    fields = agent_install.install_fields(OPENCODE, [], lambda m: None)
    assert fields[0].key == "INSTALL_SCOPE"
    assert agent_install.scope_field(OPENCODE).choices == ["user", "project"]


def test_uninstalling_opencode_edits_the_config_instead_of_running_a_command(
        tmp_path, monkeypatch, opencode_home):
    """There is no `opencode mcp remove`. Archiving the row while running an
    argv that does not exist would report success for a command never run."""
    cfg = tmp_path / ".config" / "opencode" / "opencode.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(json.dumps({"mcp": {"servers": {"tubematic": {"url": "u"}, "other": {}}}}))
    ex = Executor(dry_run=False)
    monkeypatch.setattr(agent_install, "_archive_agent_row", lambda adapter, *, ex: None)
    row = {"id": "opencode", "run_path": str(tmp_path / "ws"), "install_scope": "user"}
    agent_install.uninstall(OPENCODE, row, ex=ex, rep=NullReporter())
    servers = json.loads(cfg.read_text())["mcp"]["servers"]
    assert "tubematic" not in servers
    assert "other" in servers


def test_the_config_root_check_knows_where_each_agent_keeps_its_config(monkeypatch):
    """It used to compare against a hardcoded ~/.<name>, which is right for
    Codex and wrong for OpenCode — every ordinary OpenCode install would have
    been reported as running under an override."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert agent_install.config_root_conflict(OPENCODE) is None
    assert agent_install.config_root_conflict(CODEX) is None
    assert agent_install.config_root_conflict(CLAUDE) is None
    monkeypatch.setenv("XDG_CONFIG_HOME", "/somewhere/else")
    conflict = agent_install.config_root_conflict(OPENCODE)
    assert conflict and "/somewhere/else/opencode" in conflict[0]


# ── The checklist, for OpenCode ─────────────────────────────────────────────

def _opencode_row(home):
    return {"id": "opencode", "binary": "/b/opencode", "run_path": str(home / "ws"),
            "install_scope": "user", "models": ["anthropic/claude-sonnet-4-5"]}


def _install_opencode_on_disk(home, monkeypatch):
    cfg = home / ".config" / "opencode"
    (cfg / "skills" / "tubematic-operator").mkdir(parents=True)
    (cfg / "commands").mkdir(parents=True)
    # What `opencode mcp add --global` leaves behind: the registration, without
    # the options — those live in Tubematic's own document below.
    cfg.joinpath("opencode.json").write_text(json.dumps(
        {"mcp": {"servers": {"tubematic": {
            "type": "remote", "url": "u",
            "headers": OPENCODE.auth_headers(agent_install.mcp_auth())}}}}))
    (home / ".agents" / "skills" / "remotion-best-practices").mkdir(parents=True)
    (home / ".agents" / "skills" / "remotion-best-practices" / "SKILL.md").write_text("x")
    ws = home / "ws"
    ws.mkdir()
    (home / "logs").mkdir()
    monkeypatch.setattr(agent_install, "POLL_LOG_DIR", home / "logs")
    from onboard import actions, checks
    monkeypatch.setattr(actions, "POLL_LOG_DIR", home / "logs")
    monkeypatch.setattr(checks, "POLL_LOG_DIR", home / "logs")
    # Written from the installer's own list, not a second copy of it: a
    # fixture that disagrees with what deploy() writes is how a check that
    # passes on a broken install gets written.
    managed = OPENCODE.managed_config_file(ws)
    managed.parent.mkdir(parents=True, exist_ok=True)
    body = json.dumps({
        "permissions": actions.managed_permission_rules(OPENCODE),
        "mcp": {"servers": {"tubematic": OPENCODE.mcp_server_entry("u", agent_install.mcp_auth())}},
    })
    for target in OPENCODE.managed_config_files(ws):
        target.write_text(body)


def test_a_correct_opencode_install_verifies_clean(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _install_opencode_on_disk(tmp_path, monkeypatch)
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    failed = [label for label, c in items.items() if not c.ok]
    assert failed == [], failed


def test_an_opencode_global_entry_without_the_header_is_reported(tmp_path, monkeypatch):
    """The workspace document is not enough: an interactive session outside the
    workspace uses the global entry, and without the header it gets a 401."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _install_opencode_on_disk(tmp_path, monkeypatch)
    OPENCODE.config_file(tmp_path, respect_override=False).write_text(json.dumps(
        {"mcp": {"servers": {"tubematic": {"type": "remote", "url": "u"}}}}))
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    check = next(c for label, c in items.items() if "MCP token wired" in label)
    assert check.ok is False


def test_the_opencode_mcp_check_reads_the_config_not_the_cli(tmp_path, monkeypatch):
    """`opencode mcp list` reports "No MCP servers configured" for several
    seconds after any config change or service restart, so a checklist that
    believed it would tell the user to re-run an install that had just
    succeeded. The config document is the authoritative answer."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _install_opencode_on_disk(tmp_path, monkeypatch)
    from onboard import checks
    monkeypatch.setattr(checks, "_mcp_registered_user",
                        lambda b="": pytest.fail("the CLI must not be consulted"))
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    mcp = next(c for label, c in items.items() if "MCP registered" in label)
    assert mcp.ok is True


def test_a_missing_permission_config_is_reported(tmp_path, monkeypatch):
    """Without it the agent runs unrestricted, which is exactly the thing a
    post-install check exists to catch."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _install_opencode_on_disk(tmp_path, monkeypatch)
    OPENCODE.managed_config_file(tmp_path / "ws").unlink()
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    perms = next(c for label, c in items.items() if "workspace permissions" in label)
    assert perms.ok is False


def test_opencode_is_not_asked_for_claude_only_artefacts(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    labels = " ".join(items)
    assert "allowlist" not in labels
    assert "trusted" not in labels
    assert ".claude" not in labels


# ── Permission rules must WIN, not merely be present ────────────────────────

MCP_URL = "http://localhost:4100/mcp"


class _RecordingReporter(NullReporter):
    def __init__(self):
        self.warnings = []

    def warn(self, msg):
        self.warnings.append(str(msg))


def _write_perms(adapter, workspace):
    actions = __import__("onboard.actions", fromlist=["actions"])
    actions._write_agent_permissions(adapter, workspace, MCP_URL, agent_install.mcp_auth(),
                                     ex=Executor(dry_run=False), rep=NullReporter())
    return json.loads(adapter.managed_config_file(workspace).read_text())


def test_the_managed_rules_deny_what_the_agent_must_never_do(db, tmp_path, opencode_home):
    ws = tmp_path / "ws"
    ws.mkdir()
    rules = _write_perms(OPENCODE, ws)["permissions"]
    effects = {(r["action"], r["resource"]): r["effect"] for r in rules}
    assert effects[("shell", "*")] == "deny"
    assert effects[("write", "*")] == "deny"
    assert effects[("read", "*.env")] == "deny"
    # The poll logs sit outside every workspace and the prompts tell the agent
    # to read them, so reaching there is granted explicitly rather than left to
    # the auto-approval on argv.
    assert effects[("external_directory", f"{agent_install.POLL_LOG_DIR}/*")] == "allow"


def test_the_data_directory_is_denied_last(db, tmp_path, opencode_home):
    """Last, because permissions resolve last-match-wins and `read *` is
    allowed earlier. Read alone is not enough: OpenCode checks grep and glob
    against the search pattern, not a path, so leaving the workspace for the
    data directory is denied as an external directory too."""
    from onboard import actions
    ws = tmp_path / "ws"
    ws.mkdir()
    rules = _write_perms(OPENCODE, ws)["permissions"]
    data = f"{actions.DATA_ROOT}/**"
    assert rules[-2:] == [
        {"action": "external_directory", "resource": data, "effect": "deny"},
        {"action": "read", "resource": data, "effect": "deny"},
    ]
    # Neither the poll logs nor the workspace sit under it.
    for readable in (agent_install.POLL_LOG_DIR, ws):
        assert not str(readable).startswith(str(actions.DATA_ROOT))
    effects = {(r["action"], r["resource"]): r["effect"] for r in rules}
    assert effects[("external_directory", f"{agent_install.POLL_LOG_DIR}/*")] == "allow"


def test_the_checklist_fails_without_the_data_directory_deny(tmp_path, monkeypatch):
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _install_opencode_on_disk(tmp_path, monkeypatch)
    cfg = OPENCODE.managed_config_file(tmp_path / "ws")
    data = json.loads(cfg.read_text())
    data["permissions"] = [r for r in data["permissions"]
                           if not (r["action"] == "read" and r["effect"] == "deny"
                                   and r["resource"].endswith("/**"))]
    cfg.write_text(json.dumps(data))
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    perms = next(c for label, c in items.items() if "workspace permissions" in label)
    assert perms.ok is False


def test_the_managed_document_carries_the_whole_server_entry(db, tmp_path, opencode_home):
    """Not just the options. Measured: an entry carrying only `codemode`
    merges far enough for the server to connect — `mcp list` says connected,
    because the url comes from the other document — but the option does not
    apply and Code Mode stays on."""
    ws = tmp_path / "ws"
    ws.mkdir()
    entry = _write_perms(OPENCODE, ws)["mcp"]["servers"]["tubematic"]
    token_file = agent_install.mcp_auth().token_file
    assert entry == {"type": "remote", "url": MCP_URL, "codemode": False,
                     "headers": {"Authorization": f"Bearer {{file:{token_file}}}"}}


def test_writing_the_managed_config_twice_changes_nothing(db, tmp_path, opencode_home):
    """A redeploy is the normal path — it must be a no-op, not a reset."""
    ws = tmp_path / "ws"
    ws.mkdir()
    first = _write_perms(OPENCODE, ws)
    second = _write_perms(OPENCODE, ws)
    assert first == second
    rules = second["permissions"]
    assert len(rules) == len({json.dumps(r, sort_keys=True) for r in rules})


def test_a_later_contradicting_rule_cannot_survive_a_redeploy(db, tmp_path, opencode_home):
    """Permissions resolve last-match-wins, so an existing copy of a managed
    rule followed by a contradicting one would leave the later one in force
    while a membership test still said the rule was present. Verified against
    the real CLI — a `read *.env deny` followed by a `read *.env allow` read
    the credential file."""
    ws = tmp_path / "ws"
    (ws / ".opencode").mkdir(parents=True)
    OPENCODE.managed_config_file(ws).write_text(json.dumps({"permissions": [
        {"action": "shell", "resource": "*", "effect": "deny"},
        {"action": "shell", "resource": "*", "effect": "allow"},
        {"action": "read", "resource": "notes/*", "effect": "allow"},
    ]}))
    rules = _write_perms(OPENCODE, ws)["permissions"]
    assert {"action": "read", "resource": "notes/*", "effect": "allow"} in rules
    assert [r for r in rules if r["action"] == "shell"][-1]["effect"] == "deny"
    actions = __import__("onboard.actions", fromlist=["actions"])
    wanted = actions.managed_permission_rules(OPENCODE)
    assert rules[-len(wanted):] == wanted


def test_the_checklist_fails_when_a_later_rule_overrides_ours(tmp_path, monkeypatch):
    """A membership test would pass here, which is the whole point."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _install_opencode_on_disk(tmp_path, monkeypatch)
    cfg = OPENCODE.managed_config_file(tmp_path / "ws")
    data = json.loads(cfg.read_text())
    data["permissions"].append({"action": "shell", "resource": "*", "effect": "allow"})
    cfg.write_text(json.dumps(data))
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    perms = next(c for label, c in items.items() if "workspace permissions" in label)
    assert perms.ok is False


def test_the_managed_document_is_ours_to_rewrite(db, tmp_path, opencode_home):
    """Unlike the operator's config, this file is Tubematic's outright — the
    only thing it can hold is a previous copy of what is being written. So an
    unreadable one is replaced rather than reported, and the install can never
    finish with its rules unwritten."""
    ws = tmp_path / "ws"
    (ws / ".opencode").mkdir(parents=True)
    OPENCODE.managed_config_file(ws).write_text("{ this is not json")
    rep = _RecordingReporter()
    actions = __import__("onboard.actions", fromlist=["actions"])
    actions._write_agent_permissions(OPENCODE, ws, MCP_URL, agent_install.mcp_auth(),
                                     ex=Executor(dry_run=False), rep=rep)
    data = json.loads(OPENCODE.managed_config_file(ws).read_text())
    assert data["permissions"] == actions.managed_permission_rules(OPENCODE)


# ── Deregistration edits the operator's document without harming it ─────────

def test_uninstalling_opencode_preserves_comments_in_the_operators_config(
        tmp_path, monkeypatch, opencode_home):
    """There is no `opencode mcp remove`, so the entry is edited out of the
    document `mcp add` wrote. That document is the operator's, and
    reserialising it through json.dumps would delete their comments."""
    cfg = tmp_path / ".config" / "opencode" / "opencode.json"
    cfg.parent.mkdir(parents=True)
    cfg.write_text('{\n  // mine\n  "model": "anthropic/x",\n'
                   '  "mcp": {"servers": {"tubematic": {"url": "u"}, "other": {}}},\n}\n')
    ex = Executor(dry_run=False)
    monkeypatch.setattr(agent_install, "_archive_agent_row", lambda adapter, *, ex: None)
    row = {"id": "opencode", "run_path": str(tmp_path / "ws"), "install_scope": "user"}
    agent_install.uninstall(OPENCODE, row, ex=ex, rep=NullReporter())
    text = cfg.read_text()
    assert "// mine" in text
    data = OPENCODE.parse_config(text)
    assert "tubematic" not in data["mcp"]["servers"]
    assert "other" in data["mcp"]["servers"]
    assert data["model"] == "anthropic/x"


def test_an_unsafe_deregistration_is_reported_rather_than_performed(
        tmp_path, monkeypatch, opencode_home):
    """The text edit is verified before it is written, so a document the
    editor cannot read is left exactly as it is and the change is reported."""
    cfg = tmp_path / ".config" / "opencode" / "opencode.json"
    cfg.parent.mkdir(parents=True)
    text = '{"mcp": {"servers": {"tubematic": {"url": "u"}'      # unbalanced
    cfg.write_text(text)
    rep = _RecordingReporter()
    monkeypatch.setattr(agent_install, "_archive_agent_row", lambda adapter, *, ex: None)
    row = {"id": "opencode", "run_path": str(tmp_path / "ws"), "install_scope": "user"}
    agent_install.uninstall(OPENCODE, row, ex=Executor(dry_run=False), rep=rep)
    assert cfg.read_text() == text
    assert any("by hand" in m for m in rep.warnings)


def test_a_redeploy_keeps_working(db, tmp_path, opencode_home):
    ws = tmp_path / "ws"
    ws.mkdir()
    first = _write_perms(OPENCODE, ws)
    assert _write_perms(OPENCODE, ws) == first       # idempotent, not a reset


def test_the_managed_document_goes_with_the_uninstall(db, tmp_path, opencode_home):
    """It is Tubematic's, inside Tubematic's own workspace."""
    ws = tmp_path / "ws"
    ws.mkdir()
    _write_perms(OPENCODE, ws)
    row = {"id": "opencode", "run_path": str(ws), "install_scope": "user"}
    assert OPENCODE.managed_config_file(ws) in agent_install.deployed_paths(OPENCODE, row)


def test_a_workspace_that_is_already_an_opencode_project_is_refused(db, tmp_path):
    """The one case worth refusing, caught at the question — before anything is
    copied or registered, on every path that asks it, with no gate of its own."""
    ws = tmp_path / "theirs"
    (ws / ".opencode").mkdir(parents=True)
    OPENCODE.managed_config_file(ws).write_text('{"model": "anthropic/x"}')
    err = agent_install.workspace_conflict(str(ws), "opencode", db)
    assert err and "already contains an OpenCode config" in err
    # Asking changed nothing, and another agent is unaffected.
    assert OPENCODE.managed_config_file(ws).read_text() == '{"model": "anthropic/x"}'
    assert agent_install.workspace_conflict(str(ws), "claude", db) is None


def test_the_preflight_and_deploy_resolve_the_same_workspace(db, tmp_path, monkeypatch,
                                                             opencode_home):
    """Two ways of computing it could disagree, and the check would then guard
    a directory the install does not use."""
    deployed, _ = _deploy(db, tmp_path, monkeypatch, OPENCODE, INSTALL_SCOPE="user")
    values = {"AGENT_RUN_PATH": str(tmp_path / "ws"), "INSTALL_SCOPE": "user"}
    assert agent_install.resolve_workspace(OPENCODE, values) == deployed


def test_a_registered_server_without_the_options_is_reported(tmp_path, monkeypatch):
    """Registered and configured answer different questions: whether an
    interactive session outside the workspace can reach the server, and whether
    a scheduled run inside it sees the tools natively rather than behind Code
    Mode. If the checklist did not look at the second, `--status` would call an
    install healthy while the agent could not see a single one of its tools."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    _install_opencode_on_disk(tmp_path, monkeypatch)
    managed = OPENCODE.managed_config_file(tmp_path / "ws")
    data = json.loads(managed.read_text())
    data["mcp"]["servers"]["tubematic"].pop("codemode")
    managed.write_text(json.dumps(data))
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    registered = next(c for label, c in items.items() if "MCP registered" in label)
    options = next(c for label, c in items.items() if "MCP tool options" in label)
    assert registered.ok is True
    assert options.ok is False


def test_an_agents_own_workspace_is_never_refused(db, tmp_path, opencode_home):
    """The rule ate itself: a successful install creates exactly the file it
    rejects, so a re-install was refused, `current_values` fell back to the
    default path, and `upgrade.py` — which calls deploy() with those values —
    deployed somewhere the agents row did not point at."""
    ws = tmp_path / "my-custom-dir"
    ws.mkdir()
    _write_perms(OPENCODE, ws)
    _opencode_agent_row(db, ws)
    assert agent_install.workspace_conflict(str(ws), "opencode", db) is None
    assert agent_install.current_values("opencode", db)["AGENT_RUN_PATH"] == str(ws)


def test_a_different_directory_with_a_config_is_still_refused(db, tmp_path, opencode_home):
    ws = tmp_path / "my-custom-dir"
    ws.mkdir()
    _write_perms(OPENCODE, ws)
    _opencode_agent_row(db, ws)
    theirs = tmp_path / "theirs"
    (theirs / ".opencode").mkdir(parents=True)
    OPENCODE.managed_config_file(theirs).write_text("{}")
    assert "already contains an OpenCode config" in \
        agent_install.workspace_conflict(str(theirs), "opencode", db)


def test_a_jsonc_sibling_is_refused_and_reported(db, tmp_path, monkeypatch):
    """OpenCode loads `.opencode/opencode.jsonc` AFTER `.opencode/opencode.json`,
    so a single rule in the sibling outranks every rule in Tubematic's document.
    Measured: an operator `.jsonc` beside ours turned a credential deny back
    into an allow and the agent read the file."""
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    theirs = tmp_path / "theirs"
    (theirs / ".opencode").mkdir(parents=True)
    (theirs / ".opencode" / "opencode.jsonc").write_text("{}")   # only the sibling
    assert "already contains an OpenCode config" in \
        agent_install.workspace_conflict(str(theirs), "opencode", db)

    # And a MISSING one reopens the slot, which the permissions check alone
    # would report as healthy.
    _install_opencode_on_disk(tmp_path, monkeypatch)
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    assert next(c for l, c in items.items() if "every loaded config" in l).ok is True
    OPENCODE.managed_config_files(tmp_path / "ws")[1].unlink()
    items = _checks(_opencode_row(tmp_path), monkeypatch, tmp_path)
    assert next(c for l, c in items.items() if "every loaded config" in l).ok is False
    assert next(c for l, c in items.items() if "workspace permissions" in l).ok is True


def test_tubematic_occupies_every_basename_opencode_loads(db, tmp_path, opencode_home):
    """The defence, not a flourish: OpenCode loads `.opencode/opencode.jsonc`
    after `.opencode/opencode.json`, so whichever file Tubematic did not write
    outranks the one it did. Occupying both leaves no slot — probed with five
    other names in the same directory, none of which OpenCode loads."""
    ws = tmp_path / "agent-ws"
    ws.mkdir()
    _write_perms(OPENCODE, ws)
    written = OPENCODE.managed_config_files(ws)
    assert {f.name for f in written} == set(OPENCODE.CONFIG_BASENAMES)
    assert all(f.is_file() for f in written)
    bodies = {f.read_text() for f in written}
    assert len(bodies) == 1, "the documents must be identical, or one outranks the other"
    row = {"id": "opencode", "run_path": str(ws), "install_scope": "user"}
    assert set(written) <= set(agent_install.deployed_paths(OPENCODE, row))


def test_an_uninstalled_agents_workspace_is_no_longer_ours(db, tmp_path, opencode_home):
    """`--uninstall-agent` deletes the config, archives the row and KEEPS the
    workspace. A document at that path afterwards is the operator's — counting
    the archived row let a re-install rewrite it and a full uninstall delete
    it as Tubematic's."""
    ws = tmp_path / "agent-ws"
    (ws / ".opencode").mkdir(parents=True)
    _opencode_agent_row(db, ws, archived_at="2026-01-01T00:00:00Z")
    OPENCODE.managed_config_file(ws).write_text('{"model": "anthropic/x"}')
    err = agent_install.workspace_conflict(str(ws), "opencode", db)
    assert err and "already contains an OpenCode config" in err


def test_a_foreign_config_never_relocates_the_agent(db, tmp_path, opencode_home):
    """A workspace Tubematic no longer owns — the row was archived by an
    uninstall and the operator made the directory theirs. The pre-fill must
    still report the recorded path: `upgrade.py` takes these values and asks
    nothing, so falling back to the default would redeploy somewhere the row
    does not record and leave the scheduled runs on the old directory. The
    question is what refuses it, and says what to do."""
    ws = tmp_path / "agent-ws"
    (ws / ".opencode").mkdir(parents=True)
    _opencode_agent_row(db, ws, archived_at="2026-01-01T00:00:00Z")
    OPENCODE.managed_config_file(ws).write_text('{"model": "anthropic/x"}')
    assert agent_install.current_values("opencode", db)["AGENT_RUN_PATH"] == str(ws)
    assert agent_install.workspace_conflict(str(ws), "opencode", db) is not None


# ── MCP authentication (TMDEV-152) ──────────────────────────────────────────

def test_mcp_auth_points_at_the_token_file_never_the_token(tmp_path, monkeypatch):
    from tubematic_core.auth import HOST_SECRETS_DIR
    auth = agent_install.mcp_auth()
    assert auth.token_file == str(HOST_SECRETS_DIR / "mcp_token")
    # This install's interpreter running this install's helper, both absolute,
    # so cron (with its stripped PATH) runs the same thing an interactive shell does.
    python, script = shlex.split(auth.helper)
    assert Path(python).is_absolute() and Path(script).is_absolute()
    assert script == str(agent_install.REPO_ROOT / "scripts" / "mcp_auth_header.py")


def test_mcp_auth_quotes_an_install_path_with_spaces(monkeypatch):
    monkeypatch.setattr(agent_install, "REPO_ROOT", Path("/opt/my tubematic"))
    python, script = shlex.split(agent_install.mcp_auth().helper)
    assert script == "/opt/my tubematic/scripts/mcp_auth_header.py"


def test_a_codex_install_patches_the_helper_after_mcp_add(db, tmp_path, monkeypatch):
    ws, intents = _deploy(db, tmp_path, monkeypatch, CODEX, INSTALL_SCOPE="user")
    runs = [d for k, d in intents if k == "run"]
    # `codex mcp add` overwrites, so nothing is removed first.
    assert not any(" mcp remove " in r for r in runs)


def _codex_home(tmp_path, monkeypatch, text):
    home = tmp_path / "codex-home"
    home.mkdir()
    (home / "config.toml").write_text(text)
    monkeypatch.setenv("CODEX_HOME", str(home))
    return home / "config.toml"


def test_the_codex_helper_patch_writes_a_parseable_config(tmp_path, monkeypatch):
    import tomllib
    path = _codex_home(tmp_path, monkeypatch,
                       '# mine\n[mcp_servers.tubematic]\nurl = "http://localhost:4100/mcp"\n')
    auth = agent_install.mcp_auth()
    actions._patch_mcp_header_helper(CODEX, auth, ex=Executor(dry_run=False), rep=NullReporter())
    data = tomllib.loads(path.read_text())
    assert data["mcp_servers"]["tubematic"]["http_headers_helper"] == auth.helper
    assert path.read_text().startswith("# mine\n")


def test_the_codex_helper_patch_warns_when_the_entry_is_missing(tmp_path, monkeypatch):
    path = _codex_home(tmp_path, monkeypatch, 'model = "x"\n')
    rep = _RecordingReporter()
    actions._patch_mcp_header_helper(CODEX, agent_install.mcp_auth(),
                                     ex=Executor(dry_run=False), rep=rep)
    assert path.read_text() == 'model = "x"\n'
    assert any("401" in w for w in rep.warnings)


def test_the_codex_helper_patch_writes_nothing_under_dry_run(tmp_path, monkeypatch):
    path = _codex_home(tmp_path, monkeypatch, '[mcp_servers.tubematic]\nurl = "u"\n')
    ex = Executor(dry_run=True)
    actions._patch_mcp_header_helper(CODEX, agent_install.mcp_auth(), ex=ex, rep=NullReporter())
    assert "http_headers_helper" not in path.read_text()
    assert not ex.intents


def test_an_opencode_redeploy_reloads_its_config_after_registering(db, tmp_path, monkeypatch,
                                                                  opencode_home):
    """Seen live after an upgrade: OpenCode's background service kept its old,
    token-less MCP connection (401s) until something reloaded it."""
    ws, intents = _deploy(db, tmp_path, monkeypatch, OPENCODE, INSTALL_SCOPE="user")
    runs = [d for k, d in intents if k == "run"]
    add = next(i for i, r in enumerate(runs) if " mcp add " in r)
    assert runs.index("/b/opencode reload") > add


def test_agents_without_a_config_cache_are_not_reloaded(db, tmp_path, monkeypatch):
    for adapter in (CLAUDE, CODEX):
        ws, intents = _deploy(db, tmp_path, monkeypatch, adapter, INSTALL_SCOPE="user")
        assert not any(d.endswith(" reload") for k, d in intents if k == "run")


# ── Retired skills ──────────────────────────────────────────────────────────
# `_copy_skills` only ever adds, so a skill this release stopped shipping would
# survive every upgrade and keep teaching the agent a tool the server no longer
# has. The redeploy removes the retired names, and only those.

def _home(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setattr(agent_install.Path, "home", staticmethod(lambda: home))
    monkeypatch.delenv("CODEX_HOME", raising=False)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return home


def _retired_skill_roots(adapter, scope, home, ws):
    if scope == "project":
        return [adapter.project_skills_dir(ws)]
    roots = [adapter.user_skills_dir(home)]
    if adapter.COPIES_SKILLS_INTO_WORKSPACE:
        roots.append(adapter.project_skills_dir(ws))
    return roots


@pytest.mark.parametrize("adapter, scope", [
    (CLAUDE, "user"), (CLAUDE, "project"), (CODEX, "user"),
    (OPENCODE, "user"), (OPENCODE, "project")])
def test_a_redeploy_removes_a_retired_skill_from_every_root_it_writes(
        db, tmp_path, monkeypatch, adapter, scope):
    home = _home(tmp_path, monkeypatch)
    roots = _retired_skill_roots(adapter, scope, home, tmp_path / "ws")
    for root in roots:
        (root / "tubematic-gif-creator").mkdir(parents=True)
        (root / "somebody-elses-skill").mkdir()
    _, intents = _deploy(db, tmp_path, monkeypatch, adapter, INSTALL_SCOPE=scope)
    removed = [d for k, d in intents if k == "rmtree"]
    assert sorted(removed) == sorted(str(r / "tubematic-gif-creator") for r in roots)
    # A dry run records the removal and deletes nothing.
    for root in roots:
        assert (root / "tubematic-gif-creator").is_dir()


def test_the_sweep_deletes_only_the_retired_names(tmp_path):
    skills = tmp_path / "skills"
    (skills / "tubematic-gif-creator").mkdir(parents=True)
    (skills / "somebody-elses-skill").mkdir()
    (skills / "tubematic-operator").mkdir()
    agent_install._sweep_retired_skills(skills, ex=Executor(dry_run=False), rep=NullReporter())
    assert not (skills / "tubematic-gif-creator").exists()
    assert (skills / "somebody-elses-skill").is_dir()
    assert (skills / "tubematic-operator").is_dir()


def test_the_sweep_is_quiet_when_there_is_nothing_to_remove(tmp_path):
    ex = Executor(dry_run=True)
    agent_install._sweep_retired_skills(tmp_path / "absent", ex=ex, rep=NullReporter())
    assert ex.intents == []


def test_no_retired_skill_is_still_shipped():
    assert not set(agent_install.RETIRED_SKILLS) & set(SHIPPED_SKILLS)


def test_uninstalling_removes_a_retired_skill_too(tmp_path, monkeypatch):
    """An install that was never upgraded still holds the retired skill."""
    home = _home(tmp_path, monkeypatch)
    skills = home / ".codex" / "skills"
    (skills / "tubematic-gif-creator").mkdir(parents=True)
    (skills / "somebody-elses-skill").mkdir()
    row = {"id": "codex", "run_path": str(tmp_path / "ws"), "install_scope": "user"}
    assert agent_install.deployed_paths(CODEX, row) == [skills / "tubematic-gif-creator"]


def test_the_uninstaller_knows_the_same_retired_skills():
    """uninstall.py is standalone (it runs after the venv may be gone), so it
    carries its own copy of the list."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("uninstall_copy", REPO_ROOT / "uninstall.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert tuple(mod._RETIRED_SKILLS) == agent_install.RETIRED_SKILLS
