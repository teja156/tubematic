"""upgrade.py — one non-interactive command that owns the upgrade (TMDEV-96).

The ordering is the point: it used to be prose in the releases docs, and prose let the
new api migrate the database while the old renderer, MCP and dashboard were
still running against it. These tests pin the order and the gate.

upgrade.py is loaded by path. Every step is recorded as an Intent on the one
dry-run Executor, so a single list shows the order the steps really ran in.
"""
import importlib.util
import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

import onboard.actions as actions
import onboard.agent_install as agent_install
import onboard.checks as checks
import onboard.stack as stack
import onboard.state as state
from onboard.executor import Executor, Intent, NullReporter
from tubematic_core import db as tdb

REPO_ROOT = Path(__file__).resolve().parents[2]
NOW = "2026-09-19T00:00:00Z"


@pytest.fixture
def upgrade():
    spec = importlib.util.spec_from_file_location("upgrade_entry", REPO_ROOT / "upgrade.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Rep(NullReporter):
    def __init__(self):
        self.lines = []
    def ok(self, msg, *a, **k): self.lines.append(("ok", msg))
    def info(self, msg, *a, **k): self.lines.append(("info", msg))
    def warn(self, msg, *a, **k): self.lines.append(("warn", msg))
    def fail(self, msg, *a, **k):
        self.lines.append(("fail", msg))
        raise RuntimeError(msg)
    def text(self):
        return "\n".join(m for _, m in self.lines)


def _step(name):
    """A stand-in for a step: records itself on the executor it was handed."""
    def fn(*args, **kwargs):
        ex = next(a for a in list(args) + list(kwargs.values()) if isinstance(a, Executor))
        ex.intents.append(Intent("step", name))
    return fn


@pytest.fixture
def env(tmp_path, monkeypatch):
    """A migrated database, a crontab pointing at a previous install, and every
    step that would touch the machine replaced by a recorder."""
    db_path = tmp_path / "data" / "tubematic.db"
    db_path.parent.mkdir()
    tdb.migrate(db_path, backup=False)
    previous = tmp_path / "tubematic-v1.0.0"
    (previous / "scripts").mkdir(parents=True)
    cron = (f"*/30 * * * * {previous}/.venv/bin/python3 {previous}/scripts/poll.py "
            ">> /x/cron.log 2>&1\n")

    monkeypatch.setattr(state, "STATE_FILE", tmp_path / "new" / ".onboard-state.json")
    (tmp_path / "new").mkdir()
    monkeypatch.setattr(checks, "check_prerequisites", lambda mode="dev": [])
    monkeypatch.setattr(stack, "read_crontab", lambda: cron)
    monkeypatch.setattr(stack, "_reconcile_volume_devices", _step("reconcile"))
    monkeypatch.setattr(stack, "_stale_volumes", lambda: [])
    monkeypatch.setattr(stack, "apply_directories", _step("directories"))
    monkeypatch.setattr(actions, "apply_python_deps", _step("python_deps"))
    monkeypatch.setattr(actions, "apply_cron", _step("cron"))
    monkeypatch.setattr(agent_install, "deploy", _step("deploy"))
    monkeypatch.setattr(stack, "report", lambda rep, **kw: True)

    def no_migrate(*a, **k):
        raise AssertionError("upgrade.py must never run migrations — the containers do")
    monkeypatch.setattr(tdb, "migrate", no_migrate)

    class Env:
        pass
    e = Env()
    e.db_path, e.previous, e.lock = db_path, previous, tmp_path / "poll.lock"
    e.data_root = tmp_path / "tubematic-data"
    # From 2.0.0 an upgrade refuses without a dashboard password (TMDEV-152).
    from tubematic_core import auth
    e.secrets = tmp_path / "secrets"
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(e.secrets))
    auth.ensure_secrets(e.secrets)
    auth.set_admin_password(db_path, "a long enough password")
    # From 2.0.0 an upgrade refuses without an OpenAI key (TMDEV-165).
    _set_setting(db_path, "openai_api_key", "sk-test")
    monkeypatch.setattr(checks, "_mcp_auth_wired", lambda *a: True)
    return e


def _set_setting(db_path, key, value):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    con.commit()
    con.close()


def _video(db_path, vid, status):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES (?, 't', ?, ?, ?)", (vid, status, NOW, NOW))
    con.commit()
    con.close()


def _agent(db_path, agent_id, binary, archived=None):
    con = sqlite3.connect(db_path)
    con.execute("INSERT INTO agents (id, name, binary, run_path, install_scope, models, "
                "verified_at, is_default, weight, archived_at, created_at, updated_at) "
                "VALUES (?, ?, ?, '/tmp/ws', 'user', '[]', '', 1, 1, ?, ?, ?)",
                (agent_id, agent_id, binary, archived, NOW, NOW))
    con.commit()
    con.close()


def _run(upgrade, env, **kw):
    rep = _Rep()
    dry_run = kw.pop("dry_run", True)
    ex = Executor(dry_run=dry_run)
    kw.setdefault("install_mode", "release")
    kw.setdefault("data_root", env.data_root)
    code = upgrade.run_upgrade(dry_run=dry_run, force=kw.pop("force", False),
                               no_stop=kw.pop("no_stop", False), db_path=env.db_path,
                               lock_path=env.lock, rep=rep, ex=ex, **kw)
    order = [i.detail for i in ex.intents]
    return code, order, rep


def _index(order, needle):
    return next(i for i, d in enumerate(order) if needle in d)


# ── The sequence ─────────────────────────────────────────────────────────────

def test_the_steps_run_in_the_order_that_closes_the_mixed_version_window(upgrade, env):
    code, order, _ = _run(upgrade, env)
    assert code == 0
    # Images first, while the old stack still serves; then stop; then the
    # start sequence; then cron and agents, which need the new code in place.
    assert (_index(order, "python_deps") < _index(order, "docker compose pull")
            < _index(order, "docker compose stop") < _index(order, "directories")
            < _index(order, "reconcile") < _index(order, "docker compose up -d")
            < _index(order, "cron") )


def test_release_pulls_and_dev_builds(upgrade):
    for mode, verb in (("release", "pull"), ("dev", "build")):
        ex = Executor(dry_run=True)
        upgrade._fetch_images(ex, _Rep(), mode)
        assert [i.detail for i in ex.intents] == [
            f"docker compose {verb} tubematic-api tubematic-dashboard"]


def test_no_stop_skips_the_stop_but_still_starts(upgrade, env):
    code, order, rep = _run(upgrade, env, no_stop=True)
    assert code == 0
    assert not any("docker compose stop" in d for d in order)
    assert any("docker compose up -d" in d for d in order)
    assert "--no-stop" in rep.text()


def test_an_uninstalled_machine_is_sent_to_onboarding(upgrade, env, tmp_path):
    rep = _Rep()
    code = upgrade.run_upgrade(dry_run=True, force=False, no_stop=False, install_mode="release",
                               db_path=tmp_path / "none.db", lock_path=env.lock, rep=rep,
                               ex=Executor(dry_run=True))
    assert code == 1
    assert "onboard.py" in rep.text()


def test_a_prerequisite_error_blocks(upgrade, env, monkeypatch):
    from onboard.checks import CheckItem
    monkeypatch.setattr(checks, "check_prerequisites",
                        lambda mode="dev": [CheckItem("Docker daemon", False, hint="start docker")])
    # Live, not dry: a dry run downgrades prerequisite errors to warnings, the
    # same as onboarding, so it can preview on a machine that is not ready.
    code, order, _ = _run(upgrade, env, dry_run=False)
    assert code == 1
    assert order == []


def test_a_database_newer_than_this_code_is_refused(upgrade, env):
    """Running an older version's upgrade.py against a database a newer one
    migrated would start old code on a schema it may not understand."""
    con = sqlite3.connect(env.db_path)
    con.execute("INSERT INTO schema_migrations (version, name, applied_at) "
                "VALUES (9999, 'future', ?)", (NOW,))
    con.commit()
    con.close()
    code, order, rep = _run(upgrade, env)
    assert code == 1
    assert order == []
    assert "newer" in rep.text() and "Rollback" in rep.text()


# ── The gate ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["RENDERING", "VOICING"])
def test_in_flight_work_refuses_before_anything_changes(upgrade, env, status):
    _video(env.db_path, "vid_busy", status)
    code, order, rep = _run(upgrade, env)
    assert code == 1
    assert order == []
    assert "vid_busy" in rep.text()


def test_force_proceeds_past_in_flight_work(upgrade, env):
    _video(env.db_path, "vid_busy", "RENDERING")
    code, order, rep = _run(upgrade, env, force=True)
    assert code == 0
    assert any("docker compose stop" in d for d in order)


def test_a_running_agent_session_refuses(upgrade, env):
    import fcntl
    with open(env.lock, "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code, order, rep = _run(upgrade, env)
    assert code == 1 and order == []
    assert "poll.lock" in rep.text()


def test_the_gate_is_rechecked_before_the_stop(upgrade, env, monkeypatch):
    """A long build is exactly when the worker can claim a queued render. The
    stop must not kill it: refuse, leaving the new images in place."""
    def fetch_then_a_render_starts(ex, rep, mode):
        ex.intents.append(Intent("step", "fetch"))
        _video(env.db_path, "vid_late", "RENDERING")
    monkeypatch.setattr(upgrade, "_fetch_images", fetch_then_a_render_starts)
    code, order, rep = _run(upgrade, env)
    assert code == 1
    assert "fetch" in order
    assert not any("docker compose stop" in d or "up -d" in d for d in order)
    assert "vid_late" in rep.text()


# ── Agents ───────────────────────────────────────────────────────────────────

def test_installed_agents_are_redeployed_and_archived_ones_are_not(upgrade, env, monkeypatch):
    seen = []
    monkeypatch.setattr(agent_install, "deploy",
                        lambda adapter, binary, values, ex, rep: seen.append((adapter.name, binary)))
    _agent(env.db_path, "claude", "/bin/sh")
    code, _, _ = _run(upgrade, env)
    assert code == 0
    assert seen == [("claude", "/bin/sh")]

    seen.clear()
    con = sqlite3.connect(env.db_path)
    con.execute("UPDATE agents SET archived_at = ?", (NOW,))
    con.commit()
    con.close()
    _run(upgrade, env)
    assert seen == []


def test_a_missing_agent_binary_finishes_the_upgrade_but_fails_it(upgrade, env, monkeypatch):
    """The stack upgrade still completes, but the exit status says the agent is
    stranded: its MCP registration carries no token, so every call is refused
    and the pipeline would stall while looking healthy (TMDEV-152)."""
    seen = []
    monkeypatch.setattr(agent_install, "deploy", lambda *a, **k: seen.append(a))
    _agent(env.db_path, "claude", "/nonexistent/claude")
    code, order, rep = _run(upgrade, env)
    assert code == 1
    assert seen == []
    assert "/nonexistent/claude" in rep.text()
    assert "do nothing until fixed: claude" in rep.text()
    assert any("cron" in d for d in order)      # the rest of the upgrade still ran


# ── The previous install ─────────────────────────────────────────────────────

def test_the_previous_install_is_named_as_safe_to_remove(upgrade, env):
    _, _, rep = _run(upgrade, env)
    assert str(env.previous) in rep.text()


def test_onboarding_state_is_carried_forward_from_the_previous_install(upgrade, env):
    """Without it `onboard.py --status` in the new directory reports an
    uninstalled system, because the state file lives per directory."""
    (env.previous / ".onboard-state.json").write_text(
        json.dumps({"database": {"done": True, "ts": "then"}}))
    ex = Executor(dry_run=False)
    upgrade._carry_state(env.previous, "release", ex)
    written = json.loads(state.STATE_FILE.read_text())
    assert written["database"]["done"] is True
    assert written["install_mode"] == "release"
    for key in ("renderer", "dashboard", "cron"):
        assert written[key]["done"] is True


def test_state_without_a_previous_install_records_what_the_upgrade_ran(upgrade, env):
    upgrade._carry_state(None, "dev", Executor(dry_run=False))
    written = json.loads(state.STATE_FILE.read_text())
    assert written["install_mode"] == "dev"
    assert written["cron"]["done"] is True
    assert "install_config" not in written  # not run by an upgrade — not claimed


# ── The command line ─────────────────────────────────────────────────────────

def _main(upgrade, monkeypatch, *args, tty=False):
    monkeypatch.setattr(upgrade, "_bootstrap", lambda: None)
    monkeypatch.setattr(sys, "argv", ["upgrade.py", *args])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: tty)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: tty)
    try:
        upgrade.main()
    except SystemExit as exc:
        return exc.code
    return 0


def test_it_runs_without_a_terminal(upgrade, monkeypatch):
    """The whole reason it exists: scriptable, over non-interactive SSH."""
    calls = []
    monkeypatch.setattr(upgrade, "run_upgrade", lambda **kw: calls.append(kw) or 0)
    assert _main(upgrade, monkeypatch, "--force", "--no-stop", "--dry-run") == 0
    assert calls and calls[0]["force"] and calls[0]["no_stop"] and calls[0]["dry_run"]


def test_check_only_reports(upgrade, monkeypatch):
    reported = []
    monkeypatch.setattr(upgrade, "run_upgrade", lambda **kw: pytest.fail("--check changed things"))
    monkeypatch.setattr(stack, "report", lambda rep, **kw: reported.append(kw) or True)
    monkeypatch.setattr(upgrade, "_report_auth", lambda rep: True)
    assert _main(upgrade, monkeypatch, "--check") == 0
    assert reported


def test_check_fails_on_an_auth_problem_alone(upgrade, monkeypatch):
    monkeypatch.setattr(stack, "report", lambda rep, **kw: True)
    monkeypatch.setattr(upgrade, "_report_auth", lambda rep: False)
    assert _main(upgrade, monkeypatch, "--check") == 1


def test_check_exits_non_zero_when_something_needs_attention(upgrade, monkeypatch):
    monkeypatch.setattr(stack, "report", lambda rep, **kw: False)
    assert _main(upgrade, monkeypatch, "--check") == 1


def test_an_unknown_flag_is_refused(upgrade, monkeypatch, capsys):
    assert _main(upgrade, monkeypatch, "--yes") == 1
    assert "--yes" in capsys.readouterr().out


# ── Authentication (TMDEV-152) ───────────────────────────────────────────────

def test_no_password_refuses_before_anything_changes(upgrade, env):
    con = sqlite3.connect(env.db_path)
    con.execute("DELETE FROM settings WHERE key = 'admin_password_hash'")
    con.commit()
    con.close()
    code, order, rep = _run(upgrade, env)
    assert code == 1
    assert order == []
    assert "python onboard.py --set-password" in rep.text()


def test_no_stop_is_refused_while_a_token_is_missing(upgrade, env):
    (env.secrets / "mcp_token").unlink()
    code, order, rep = _run(upgrade, env, no_stop=True)
    assert code == 1
    assert order == []
    assert "--no-stop" in rep.text()


def test_no_stop_is_allowed_once_the_tokens_exist(upgrade, env):
    code, order, _ = _run(upgrade, env, no_stop=True)
    assert code == 0


# ── OpenAI becomes the only image provider (TMDEV-165) ───────────────────────

@pytest.mark.parametrize("stored", [None, "", "   "])
def test_no_openai_key_refuses_before_anything_changes(upgrade, env, stored):
    """Otherwise the upgrade succeeds and every scene image then fails — after a
    human approved the script and the voicing was paid for."""
    con = sqlite3.connect(env.db_path)
    con.execute("DELETE FROM settings WHERE key = 'openai_api_key'")
    if stored is not None:
        con.execute("INSERT INTO settings (key, value) VALUES ('openai_api_key', ?)", (stored,))
    con.commit()
    con.close()
    code, order, rep = _run(upgrade, env)
    assert code == 1
    assert order == []
    assert "No OpenAI API key is stored" in rep.text()
    assert "Settings" in rep.text()


def test_a_gemini_key_alone_does_not_satisfy_the_upgrade(upgrade, env):
    con = sqlite3.connect(env.db_path)
    con.execute("DELETE FROM settings WHERE key = 'openai_api_key'")
    con.commit()
    con.close()
    _set_setting(env.db_path, "gemini_api_key", "AIza-key")
    code, order, _ = _run(upgrade, env)
    assert code == 1
    assert order == []


def test_no_stop_is_refused_while_the_image_migration_is_pending(upgrade, env):
    """Old containers recreated one at a time would keep reading the
    image_provider row 0016 deletes."""
    con = sqlite3.connect(env.db_path)
    con.execute("DELETE FROM schema_migrations WHERE version >= ?",
                (upgrade.OPENAI_ONLY_IMAGES_MIGRATION,))
    con.commit()
    con.close()
    code, order, rep = _run(upgrade, env, no_stop=True)
    assert code == 1
    assert order == []
    assert "--no-stop" in rep.text() and "image provider" in rep.text()


def test_the_pending_image_migration_still_allows_a_normal_upgrade(upgrade, env):
    con = sqlite3.connect(env.db_path)
    con.execute("DELETE FROM schema_migrations WHERE version >= ?",
                (upgrade.OPENAI_ONLY_IMAGES_MIGRATION,))
    con.commit()
    con.close()
    code, _, _ = _run(upgrade, env)
    assert code == 0


def test_the_image_migration_constant_names_the_real_migration(upgrade):
    from tubematic_core import db as tdb_real
    names = {m.version: m.name for m in tdb_real.discover()}
    assert names[upgrade.OPENAI_ONLY_IMAGES_MIGRATION] == "openai_only_images"


def test_the_upgrade_creates_missing_tokens_before_up(upgrade, env):
    """Compose refuses to start a service whose token file is missing."""
    from tubematic_core import auth
    for name in auth.SECRET_NAMES:
        (env.secrets / name).unlink()
    code, order, _ = _run(upgrade, env)
    assert code == 0
    assert order.index(str(env.secrets)) < _index(order, "docker compose up -d")


def test_an_agent_redeployed_without_its_token_is_stranded(upgrade, env, monkeypatch):
    monkeypatch.setattr(agent_install, "deploy", lambda *a, **k: Path("/tmp/ws"))
    monkeypatch.setattr(checks, "_mcp_auth_wired", lambda *a: False)
    _agent(env.db_path, "claude", "/bin/sh")
    rep = _Rep()
    assert upgrade._redeploy_agents(Executor(dry_run=False), rep, env.db_path) == ["claude"]
    assert "carries no token" in rep.text()


def test_a_correctly_redeployed_agent_is_not_stranded(upgrade, env, monkeypatch):
    monkeypatch.setattr(agent_install, "deploy", lambda *a, **k: Path("/tmp/ws"))
    _agent(env.db_path, "claude", "/bin/sh")
    assert upgrade._redeploy_agents(Executor(dry_run=False), _Rep(), env.db_path) == []


# ── Removed GifFX component ──────────────────────────────────────────────────
# The renderer bundles every generated scene together, so one scene importing
# the removed GifFX component fails every render on the install. The upgrade
# refuses before anything changes; a scene-config naming it only loses that
# overlay on a re-render (an unloadable scene is skipped), so that one warns.

def _scene(env, rel, text):
    path = env.data_root / "scenes" / "generated" / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _scene_config(env, vid, text):
    path = env.data_root / "jobs" / vid / "scene-config.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def test_a_scene_importing_giffx_refuses_before_anything_changes(upgrade, env):
    bad = _scene(env, "vid_aaaaaaaaaaaa/confetti.tsx",
                 'import GifFX from "../../installed/GifFX";\nexport default GifFX;\n')
    code, order, rep = _run(upgrade, env)
    assert code == 1
    assert order == []
    assert str(bad) in rep.text() and "GifFX" in rep.text()


def test_clean_generated_scenes_pass(upgrade, env):
    _scene(env, "vid_aaaaaaaaaaaa/intro.tsx",
           'import ImageFX from "../../installed/ImageFX";\nexport default ImageFX;\n')
    _scene(env, "legacy-flat.tsx", "export default () => null;\n")
    code, _, rep = _run(upgrade, env)
    assert code == 0
    assert "GifFX" not in rep.text()


def test_no_generated_scenes_directory_passes(upgrade, env):
    code, _, _ = _run(upgrade, env)
    assert code == 0


def test_a_scene_config_naming_giffx_only_warns(upgrade, env):
    cfg = _scene_config(env, "vid_bbbbbbbbbbbb",
                        json.dumps({"scenes": [{"type": "generated", "src": "GifFX",
                                                "source": "installed"}]}))
    _scene_config(env, "vid_cccccccccccc",
                  json.dumps({"scenes": [{"type": "generated", "src": "ImageFX"}]}))
    code, order, rep = _run(upgrade, env)
    assert code == 0
    assert order != []
    warned = [m for k, m in rep.lines if k == "warn" and "GifFX" in m]
    assert warned and str(cfg) in warned[0]
    assert "vid_cccccccccccc" not in rep.text()


@pytest.mark.parametrize("line", [
    'import GifFX from "../../installed/./GifFX";',
    'import GifFX from "../../installed//GifFX";',
    'import GifFX from "../../installed/GifFX.tsx";',
    "import GifFX from '../../installed/sub/../GifFX';",
    'import {\n  default as GifFX,\n} from\n  "../../installed/GifFX";',
    'export { default } from "../../installed/GifFX";',
    'import "../../installed/GifFX";',
    'const G = React.lazy(() => import("../../installed/GifFX"));',
    'const G = import(\n  `../../installed/GifFX`\n);',
    'const G = require("../../installed/GifFX").default;',
    # Comments between the tokens, which TypeScript accepts.
    'import GifFX from /* comment */ "../../installed/GifFX";',
    'const GifFX = import/* comment */("../../installed/GifFX");',
    'const GifFX = require/* comment */("../../installed/GifFX");',
    'import GifFX from // where it lives\n  "../../installed/GifFX";',
    'const G = import(/* webpackChunkName: "gif" */ "../../installed/GifFX");',
    # A "//" inside a string is not a comment: the import after it still counts.
    'const u = "https://example.com"; import GifFX from "../../installed/GifFX";',
    'import type { GifFXProps } from "../../installed/GifFX";',
    # String escapes, decoded to the value the bundler resolves.
    'import GifFX from "../../installed/\\u0047ifFX";',
    'import GifFX from "../../installed/\\u{47}ifFX";',
    'import GifFX from "../../installed/\\x47ifFX";',
    'import GifFX from "../../installed/\\GifFX";',
    'import GifFX from "../../installed/Gif\\\nFX";',
    'const G = require(`../../installed/\\u0047ifFX`);',
    # Computed paths: webpack folds the constant parts, or builds a context
    # module over installed/ that holds GifFX.
    'const G = require("../../installed/" + "GifFX");',
    'const G = import("../../installed/" + "GifFX");',
    'const G = import(`../../installed/${"GifFX"}`);',
    'const base = "../../installed/"; const G = require(base + "GifFX");',
    # Other call shapes webpack treats as require(): parenthesised, optional,
    # and its resolve APIs, which still add the module to the bundle.
    'const G = (require)("../../installed/GifFX");',
    'const G = ((require))("../../installed/GifFX");',
    'const G = require?.("../../installed/GifFX");',
    'const G = require.resolve("../../installed/GifFX");',
    'const G = require.resolveWeak("../../installed/GifFX");',
    'const G = require /* c */ . resolve("../../installed/" + "GifFX");',
    # Its bracket spellings, which webpack bundles the same way.
    'const G = require["resolve"]("../../installed/GifFX");',
    'const G = require["resolveWeak"]("../../installed/GifFX");',
    'const G = (require)["resolve"]("../../installed/GifFX");',
    "const G = require /* a */ [ /* b */ `resolve` /* c */ ] /* d */ (\"../../installed/GifFX\");",
    # Any other key, literal or not, is not told apart from those: a call on
    # it refuses when its argument names GifFX (fail closed).
    'const G = require["cache"]("../../installed/GifFX");',
    'const G = require[key]("../../installed/GifFX");',
    # A method named require on another object is not webpack's require, but
    # the check does not tell them apart: it fails closed and refuses.
    'const G = loader.require("../../installed/GifFX");',
])
def test_every_spelling_of_a_giffx_import_refuses(upgrade, env, line):
    """The module specifier is what the bundler resolves, so it is what is
    normalised and compared — not a literal substring of the file."""
    bad = _scene(env, "vid_aaaaaaaaaaaa/confetti.tsx", line + "\nexport default null;\n")
    code, order, rep = _run(upgrade, env)
    assert code == 1 and order == []
    assert str(bad) in rep.text()


def test_a_component_merely_named_like_giffx_passes(upgrade, env):
    """Resolution is case-sensitive on Linux, and a name that only contains
    GifFX is a different module."""
    _scene(env, "vid_aaaaaaaaaaaa/a.tsx",
           'import X from "../../installed/GifFXLegacy";\n'
           'import Y from "./GifFX";\n'
           '// GifFX used to live in installed/GifFX\nexport default X;\n')
    code, _, _ = _run(upgrade, env)
    assert code == 0


@pytest.mark.parametrize("line", [
    'const G = import("./" + "GifFX");',
    'const G = import(`./${"GifFX"}`);',
])
def test_a_computed_path_naming_a_local_giffx_refuses(upgrade, env, line):
    """A known limitation, kept on purpose: a computed path is not resolved, so
    one that only names a sibling ./GifFX refuses like one naming
    installed/GifFX. The static `import Y from "./GifFX"` passes (above)."""
    bad = _scene(env, "vid_aaaaaaaaaaaa/a.tsx", line + "\nexport default null;\n")
    code, order, rep = _run(upgrade, env)
    assert code == 1 and order == []
    assert str(bad) in rep.text()


def test_every_scene_in_the_repository_scans_clean(upgrade):
    """The lexer reads every .tsx this repository ships — installed
    components, examples, the renderer — without a false refusal."""
    tsx = []
    for root, dirs, files in os.walk(REPO_ROOT):
        dirs[:] = [d for d in dirs if d not in ("node_modules", ".git", ".worktrees")]
        tsx += [Path(root, f) for f in files if f.endswith(".tsx")]
    assert len(tsx) > 50
    for path in tsx:
        assert upgrade._imports_giffx(path.read_text()) is False, path


@pytest.mark.parametrize("text", [
    'const u = "https://example.com/a"; // a comment\n'
    'import ImageFX from "../../installed/ImageFX";\nexport default ImageFX;\n',
    '// was GifFX\nimport ImageFX from "../../installed/ImageFX";\n',
    '/* GifFX, before it was removed */ import X from "../../installed/GifFXNew";\n',
    'const dash = "\\u2014"; import ImageFX from "../../installed/ImageFX";\n',
    # The whole old import, kept as a note: a comment or a string imports nothing.
    '// import GifFX from "../../installed/GifFX";\n'
    'import ImageFX from "../../installed/ImageFX";\n',
    '/* const G = import("../../installed/GifFX"); */\nexport default null;\n',
    '/*\n * Was: import GifFX from "../../installed/GifFX";\n */\nexport default null;\n',
    'const note = \'import GifFX from "../../installed/GifFX"\';\n',
    'const doc = `import GifFX from "../../installed/GifFX"`;\n',
    'const where = "../../installed/GifFX"; // a path in a string imports nothing\n',
    'const G = import("../../installed/" + "ImageFX");\n',
    # A bracket key is not a module path, and only require's own key counts.
    'delete require["cache"]["../../installed/GifFX"];\n',
    'const m = require["cache"]("./local");\n',
    'const r = registry["resolve"]("../../installed/GifFX");\n',
])
def test_text_that_only_mentions_giffx_passes(upgrade, env, text):
    """Negative controls: a string holding "//", a comment naming GifFX, a
    different module, an ordinary escape in a string, and the whole old import
    kept in a comment or a string all leave the upgrade alone."""
    _scene(env, "vid_aaaaaaaaaaaa/a.tsx", text)
    code, _, rep = _run(upgrade, env)
    assert code == 0
    assert "GifFX" not in rep.text()


@pytest.mark.parametrize("line", [
    'import X from "../../installed/\\8ifFX";',
    'import X from "../../installed/\\x4";',
    'import X from "../../installed/\\u{110000}";',
    'const X = require("../../installed/" + "\\8ifFX");',
])
def test_a_module_path_that_cannot_be_decoded_refuses(upgrade, env, line):
    """An escape the upgrade cannot decode could be hiding installed/GifFX,
    so it fails closed. TypeScript rejects these escapes too."""
    bad = _scene(env, "vid_aaaaaaaaaaaa/odd.tsx", line + "\nexport default X;\n")
    code, order, rep = _run(upgrade, env)
    assert code == 1 and order == []
    assert str(bad) in rep.text() and "decode" in rep.text()


_JSX_SCENE = (
    'import ImageFX from "../../installed/ImageFX";\n'
    "export default () => (\n"
    "  <AbsoluteFill>\n"
    "    <p>Don't panic: every file in src/* is `fine</p>\n"
    "    <a href=\"https://example.com\">https://example.com</a>\n"
    "  </AbsoluteFill>\n"
    ");\n")


@pytest.mark.parametrize("text, refuses", [
    # JSX text is not code: its apostrophe, backtick and "/*" open nothing, so a real import after it is still found ...
    (_JSX_SCENE + 'const G = require("../../installed/GifFX");\n', True),
    # ... and without one the scene passes, even with the old import kept as
    # a note after the text (read as code, its "/*" would run to the end).
    (_JSX_SCENE, False),
    (_JSX_SCENE + '// Was: import GifFX from "../../installed/GifFX";\n', False),
    # A regex holding a quote or a backtick is not a string or a template.
    ("const q = /'/g;\nconst G = require(\"../../installed/GifFX\");\n", True),
    ("const t = /`/;\n// import GifFX from \"../../installed/GifFX\"\nexport default t;\n",
     False),
    # A misread the lexer cannot place errs only towards refusing: a stray
    # quote never hides the lines after it ...
    ("const n = 1 <p>don't</p>;\nconst G = require(\"../../installed/GifFX\");\n", True),
    # JSX text is lexed as code in case it was code misread as JSX: import
    # words alone pass, but a call cut off by a `{…}` cannot be judged and
    # refuses.
    ("export default () => <p>Import from a file, then require it.</p>;\n", False),
    ("export default () => <p>Use require({path}) here.</p>;\n", True),
    # So does text ending in `import` or `require` (a word awaiting its path
    # or call) at a tag or a `{…}`: a known cost, kept on purpose, since the
    # rest of that call is not lexed as code. `from` before `{…}` is ordinary
    # prose, and passes.
    ("export default () => <p>The modules you require.</p>;\n", True),
    ("export default () => <p>Packets from {src} to {dst}</p>;\n", False),
])
def test_jsx_text_and_regexes_never_hide_an_import(upgrade, env, text, refuses):
    path = _scene(env, "vid_aaaaaaaaaaaa/a.tsx", text)
    code, order, rep = _run(upgrade, env)
    if refuses:
        assert code == 1 and order == [] and str(path) in rep.text()
    else:
        assert code == 0 and "GifFX" not in rep.text()


# TSX reads `<T,>`, `<T = …>` and `<T extends …>` as a generic arrow's type
# parameters; the lexer must stay in code after them. A bare `<T>` is JSX in
# TSX (it does not compile), so it stands for text the lexer misreads as JSX:
# that is still lexed as code, so a misreading neither hides an import nor
# refuses a note.
_GENERIC_HEADS = [
    "const id = <T extends unknown>(x: T) => x; // it's\n",
    "const id = <T,>(x: T) => x; // it's\n",
    "const id = <T extends object = {}>(x: T) => x; // it's\n",
    "const id = <const T extends readonly string[]>(x: T) => x; // it's\n",
    # A type parameter may start with any Unicode letter.
    "const id = <É extends unknown>(x: É) => x; // it's\n",
    "const id = <T>(x: T) => x; // it's\n",
]


@pytest.mark.parametrize("head", _GENERIC_HEADS)
@pytest.mark.parametrize("body, refuses", [
    ('const G = require("../../installed/GifFX");\n', True),
    ('const G = require("../../installed/\\u0047ifFX");\n', True),
    ('const G = require("../../installed/" + "Gif" + "FX");\n', True),
    ('const G = import(`../../installed/${"GifFX"}`);\n', True),
    ('// import GifFX from "../../installed/GifFX";\nexport default id;\n', False),
    ('/* const G = require("../../installed/GifFX"); */\nexport default id;\n', False),
    ('const note = \'import GifFX from "../../installed/GifFX"\';\n', False),
    ("export default id;\n", False),
])
def test_an_import_after_a_generic_arrow_is_still_judged_as_code(upgrade, head, body, refuses):
    assert upgrade._imports_giffx(head + body) is refuses


@pytest.mark.parametrize("head", _GENERIC_HEADS[:-1])
def test_code_after_a_generic_arrow_is_not_read_as_jsx(upgrade, head):
    """Misread as JSX text, this call would be cut off at its `{` and refuse
    (as it does after the bare `<T>`)."""
    body = 'const G = require(pick({ name: "ImageFX" }));\n'
    assert upgrade._imports_giffx(head + body) is False
    assert upgrade._imports_giffx(_GENERIC_HEADS[-1] + body) is True


# Code misread as JSX text is lexed in chunks, split at every "<" and "{" —
# even one inside a comment or a bracket key. A chunk that ends between an
# import word and its path or call cannot be judged, so it refuses.
@pytest.mark.parametrize("head", ["const id = <É extends unknown>(x: É) => x;\n",
                                  "const id = <T>(x: T) => x;\n"])
@pytest.mark.parametrize("body", [
    'const G = require /* < */ ("../../installed/GifFX");\n',
    'const G = import /* { */ ("../../installed/GifFX");\n',
    'const G = require // <\n  ("../../installed/GifFX");\n',
    'const G = require /* < */ .resolve("../../installed/GifFX");\n',
    'const G = require["<"]("../../installed/GifFX");\n',
    'import G from /* < */ "../../installed/GifFX";\n',
    'import G from // <\n  "../../installed/GifFX";\n',
])
def test_an_import_split_inside_misread_jsx_refuses(upgrade, head, body):
    assert upgrade._imports_giffx(head + body) is True


# JSX text after a comparison (`1 <p>`) is read as code, so its "/*" or
# backtick never closes. The rest of the file is lexed as code, not skipped
# and not searched as raw text.
@pytest.mark.parametrize("head", ["const n = 1 <p>src/* x</p>;\n",
                                  "const n = 1 <p>it's `x</p>;\n",
                                  # an attribute value, a closing tag that never closes
                                  "export default () => <a title='x>;\n",
                                  "const id = <T>(x: T) => x </ 1;\n"])
@pytest.mark.parametrize("body, refuses", [
    ('const G = require("../../installed/\\u0047ifFX");\n', True),
    ('const G = require("../../installed/" + "Gif" + "FX");\n', True),
    ('// import GifFX from "../../installed/GifFX";\nexport default n;\n', False),
    ('const note = \'import GifFX from "../../installed/GifFX"\';\n', False),
])
def test_a_comment_template_or_tag_that_never_closes_hides_nothing(upgrade, head, body,
                                                                    refuses):
    assert upgrade._imports_giffx(head + body) is refuses


def test_an_unreadable_generated_scene_refuses(upgrade, env, monkeypatch):
    """The renderer could not compile it either, so the upgrade fails closed."""
    bad = _scene(env, "vid_aaaaaaaaaaaa/locked.tsx", "export default null;\n")
    real = Path.read_text
    def read_text(self, *a, **k):
        if self == bad:
            raise PermissionError(13, "Permission denied")
        return real(self, *a, **k)
    monkeypatch.setattr(Path, "read_text", read_text)
    code, order, rep = _run(upgrade, env)
    assert code == 1 and order == []
    assert str(bad) in rep.text()


def test_a_scene_written_during_the_build_refuses_before_the_stop(upgrade, env, monkeypatch):
    """The old MCP server keeps serving through the build and can still write
    a GifFX scene. The check runs again, under the poll lock, after the last
    work gate — before anything is stopped."""
    def fetch_then_a_scene_lands(ex, rep, mode):
        ex.intents.append(Intent("step", "fetch"))
        _scene(env, "vid_dddddddddddd/late.tsx",
               'import GifFX from "../../installed/GifFX";\nexport default GifFX;\n')
    monkeypatch.setattr(upgrade, "_fetch_images", fetch_then_a_scene_lands)
    code, order, rep = _run(upgrade, env)
    assert code == 1
    assert "fetch" in order
    assert not any("docker compose stop" in d or "up -d" in d for d in order)
    assert "late.tsx" in rep.text()


def test_a_scene_written_during_the_build_refuses_under_no_stop(upgrade, env, monkeypatch):
    def fetch_then_a_scene_lands(ex, rep, mode):
        ex.intents.append(Intent("step", "fetch"))
        _scene(env, "vid_dddddddddddd/late.tsx", 'import G from "../../installed/GifFX";\n')
    monkeypatch.setattr(upgrade, "_fetch_images", fetch_then_a_scene_lands)
    code, order, rep = _run(upgrade, env, no_stop=True)
    assert code == 1
    assert not any("up -d" in d for d in order)
