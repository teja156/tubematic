"""uninstall.py's install-config read must survive database deletion.

The config used to come from .env, which uninstall removes at step 7 — after
every consumer had run. TMDEV-73 moved it into the database, which step 3
removes, *before* remove_claude_integration needs the install scope and agent
workspace path. Without a cache, a confirmed database deletion leaves step 5
with nothing to read: it prompts (defeating --force) or skips removing a
project-level workspace because the path is gone.
"""
import importlib.util
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


@pytest.fixture
def uninstall(tmp_path, monkeypatch):
    """A fresh uninstall module rooted at tmp_path (its cache is global)."""
    spec = importlib.util.spec_from_file_location(
        f"uninstall_{tmp_path.name}", REPO_ROOT / "uninstall.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(mod, "DATA_ROOT", tmp_path)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.executemany("INSERT INTO settings VALUES (?, ?)", [
        ("install_scope", "project"),
        ("agent_run_path", "/srv/agent-workspace"),
    ])
    con.commit()
    con.close()
    mod._db = db
    return mod


def test_reads_scope_and_workspace_from_settings(uninstall):
    env = uninstall._install_config()
    assert env["INSTALL_SCOPE"] == "project"
    assert env["AGENT_RUN_PATH"] == "/srv/agent-workspace"


def _add_agent_row(db, scope="user", run_path="/srv/claude-ws"):
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE agents (id TEXT PRIMARY KEY, install_scope TEXT, run_path TEXT)")
    con.execute("INSERT INTO agents VALUES ('claude', ?, ?)", (scope, run_path))
    con.commit()
    con.close()


def test_the_claude_agent_row_wins_over_legacy_settings_rows(uninstall):
    """Since TMDEV-90 the scope and workspace live on the agents row; the
    settings rows survive only on an install that has not re-installed its
    agent since upgrading."""
    _add_agent_row(uninstall._db)
    env = uninstall._install_config()
    assert env["INSTALL_SCOPE"] == "user"
    assert env["AGENT_RUN_PATH"] == "/srv/claude-ws"


def test_no_agents_table_falls_back_to_settings(uninstall):
    """A pre-TMDEV-90 database has no agents table at all — not an error."""
    env = uninstall._install_config()
    assert env["AGENT_RUN_PATH"] == "/srv/agent-workspace"


def test_a_primed_read_survives_database_deletion(uninstall):
    """The regression guard: main() primes the cache before remove_database()."""
    uninstall._install_config()          # primed, as main() does
    uninstall._db.unlink()               # remove_database()
    env = uninstall._install_config()    # remove_claude_integration()
    assert env["INSTALL_SCOPE"] == "project"
    assert env["AGENT_RUN_PATH"] == "/srv/agent-workspace"


def test_an_unprimed_read_after_deletion_degrades_to_empty(uninstall):
    """Without the prime there is nothing to recover — which is exactly why
    main() must prime. Pinned so the ordering requirement stays visible."""
    uninstall._db.unlink()
    assert uninstall._install_config() == {}


def test_missing_database_is_not_an_error(uninstall):
    uninstall._db.unlink()
    assert uninstall._install_config() == {}


def test_force_never_blocks_on_the_scope_prompt(uninstall, monkeypatch, capsys):
    """--force implies non-interactive. The scope fallback used a bare input(),
    which raises EOFError on a piped run instead of falling back."""
    uninstall._db.unlink()
    uninstall._INSTALL_CONFIG_CACHE = None
    monkeypatch.setattr(uninstall, "FORCE", True)
    monkeypatch.setattr(uninstall, "_remove_user_level_integration", lambda: None)
    monkeypatch.setattr(uninstall, "input",
                        lambda *a: pytest.fail("--force must not prompt"), raising=False)
    uninstall.remove_claude_integration()
    assert "assuming user-level" in capsys.readouterr().out


def test_main_primes_the_cache_before_deleting_anything(uninstall, monkeypatch):
    """Order is the whole fix — assert it directly rather than trusting it."""
    order = []
    monkeypatch.setattr(uninstall, "FORCE", True)
    for name in ("stop_containers", "remove_docker_volumes", "remove_job_files",
                 "remove_claude_integration", "remove_cron", "remove_env",
                 "print_summary"):
        monkeypatch.setattr(uninstall, name, lambda: None)
    monkeypatch.setattr(uninstall, "remove_database",
                        lambda: order.append("remove_database"))
    real = uninstall._install_config
    monkeypatch.setattr(uninstall, "_install_config",
                        lambda: (order.append("_install_config"), real())[1])
    monkeypatch.setattr(sys, "argv", ["uninstall.py", "--force"])
    uninstall.main()
    assert order.index("_install_config") < order.index("remove_database")


# ── Data-root cleanup (TMDEV-76 follow-up) ──────────────────────────────────
# Under the old repo-relative mounted/ tree, `rm -rf tubematic` finished the
# job. The data root now sits outside the checkout, so nothing removes it
# unless uninstall does — and generated scenes had no step at all.

@pytest.fixture
def populated(uninstall, tmp_path, monkeypatch):
    """A data root with content in every subdirectory."""
    root = tmp_path / ".tubematic-data"
    monkeypatch.setattr(uninstall, "DATA_ROOT", root)
    for sub, name in [("data", "tubematic.db"), ("jobs", "vid_a/audio.mp3"),
                      ("output_videos", "proj/vid_a.mp4"), ("scenes/generated", "vid_a/Scene.tsx")]:
        f = root / sub / name
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("x" * 1024)
    monkeypatch.setattr(uninstall, "FORCE", False)
    return root


def _answer(uninstall, monkeypatch, value):
    monkeypatch.setattr(uninstall, "confirm", lambda *a, **k: value)


def test_scenes_step_deletes_generated_scenes(uninstall, populated, monkeypatch):
    _answer(uninstall, monkeypatch, True)
    uninstall.remove_scenes()
    assert not list((populated / "scenes" / "generated").iterdir())


def test_scenes_step_declined_keeps_them(uninstall, populated, monkeypatch):
    _answer(uninstall, monkeypatch, False)
    uninstall.remove_scenes()
    assert (populated / "scenes" / "generated" / "vid_a" / "Scene.tsx").exists()


def test_scenes_step_with_nothing_to_do_is_not_an_error(uninstall, tmp_path, monkeypatch):
    monkeypatch.setattr(uninstall, "DATA_ROOT", tmp_path / "empty")
    uninstall.remove_scenes()  # must not raise


def test_data_root_step_can_delete_everything(uninstall, populated, monkeypatch):
    _answer(uninstall, monkeypatch, True)
    uninstall.remove_data_root()
    assert not populated.exists()


def test_data_root_step_declined_keeps_the_videos(uninstall, populated, monkeypatch):
    """Default is NO and the videos are the product — declining must be safe."""
    _answer(uninstall, monkeypatch, False)
    uninstall.remove_data_root()
    assert (populated / "output_videos" / "proj" / "vid_a.mp4").exists()


def test_data_root_step_names_the_videos_in_the_prompt(uninstall, populated, monkeypatch):
    """The count has to be in the question itself — it is the one irreversible
    thing the script does, and a generic 'delete this directory?' hides it."""
    asked = {}
    monkeypatch.setattr(uninstall, "confirm",
                        lambda q, **k: asked.setdefault("q", q) and False)
    uninstall.remove_data_root()
    assert "1 rendered video" in asked["q"]


def test_data_root_step_prunes_empty_subdirs_when_declined(uninstall, populated, monkeypatch):
    """After the earlier steps have run, what is left should be only the things
    worth keeping — not a scaffold of empty directories."""
    for p in [populated / "data" / "tubematic.db",
              populated / "jobs" / "vid_a" / "audio.mp3",
              populated / "scenes" / "generated" / "vid_a" / "Scene.tsx"]:
        shutil.rmtree(p.parent) if p.parent != populated / "data" else p.unlink()
    _answer(uninstall, monkeypatch, False)
    uninstall.remove_data_root()
    assert not (populated / "data").exists()
    assert (populated / "output_videos").exists()


def test_data_root_step_with_no_root_is_not_an_error(uninstall, tmp_path, monkeypatch):
    monkeypatch.setattr(uninstall, "DATA_ROOT", tmp_path / "gone")
    uninstall.remove_data_root()  # must not raise


def test_main_runs_both_new_steps_last(uninstall, monkeypatch):
    """remove_data_root must come after everything that clears a subdirectory,
    or its empty-prune finds nothing to prune."""
    order = []
    monkeypatch.setattr(uninstall, "FORCE", True)
    for name in ("stop_containers", "remove_docker_volumes", "remove_database",
                 "remove_job_files", "remove_claude_integration", "remove_cron",
                 "remove_env", "print_summary"):
        monkeypatch.setattr(uninstall, name, lambda n=name: order.append(n))
    monkeypatch.setattr(uninstall, "remove_scenes", lambda: order.append("remove_scenes"))
    monkeypatch.setattr(uninstall, "remove_data_root", lambda: order.append("remove_data_root"))
    monkeypatch.setattr(sys, "argv", ["uninstall.py", "--force"])
    uninstall.main()
    assert "remove_scenes" in order
    assert order.index("remove_scenes") > order.index("remove_job_files")
    assert order.index("remove_data_root") == len(order) - 2  # just before the summary


# ── Non-Claude agent sweep ──────────────────────────────────────────────────
# The whole-project uninstaller only ever removed Claude's files. A Codex
# install kept its skills in ~/.codex/skills and a global MCP registration, so
# "uninstall Tubematic" used to leave both behind. The sweep is now driven off
# the adapters, so these drive it through the same generic entry point that
# every agent goes through rather than through a per-agent function.


def _sweep(uninstall, agent: str):
    adapters = uninstall._load_adapters()
    assert adapters, "uninstall.py could not load scripts/agent_adapters.py"
    return uninstall._remove_agent_integration(adapters[agent], 6)

def _codex_home(uninstall, tmp_path, monkeypatch, skills=("tubematic-operator",)):
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    d = tmp_path / ".codex" / "skills"
    for name in skills:
        (d / name).mkdir(parents=True)
    return d


def test_codex_skills_are_removed(uninstall, tmp_path, monkeypatch):
    skills = _codex_home(uninstall, tmp_path, monkeypatch)
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    _sweep(uninstall, "codex")
    assert not (skills / "tubematic-operator").exists()


def test_declining_keeps_the_codex_skills(uninstall, tmp_path, monkeypatch):
    skills = _codex_home(uninstall, tmp_path, monkeypatch)
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, False)
    _sweep(uninstall, "codex")
    assert (skills / "tubematic-operator").exists()


def test_only_tubematic_skills_are_touched(uninstall, tmp_path, monkeypatch):
    skills = _codex_home(uninstall, tmp_path, monkeypatch)
    (skills / "somebody-elses-skill").mkdir()
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    _sweep(uninstall, "codex")
    assert (skills / "somebody-elses-skill").exists()


def test_the_codex_mcp_registration_is_deregistered(uninstall, tmp_path, monkeypatch):
    _codex_home(uninstall, tmp_path, monkeypatch)
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: "/b/codex" if n == "codex" else None)
    calls = []
    monkeypatch.setattr(uninstall.subprocess, "run",
                        lambda cmd, **kw: calls.append(cmd) or
                        __import__("types").SimpleNamespace(returncode=0, stderr=""))
    _answer(uninstall, monkeypatch, True)
    _sweep(uninstall, "codex")
    assert ["/b/codex", "mcp", "remove", "tubematic"] in calls


def test_a_machine_that_never_had_codex_is_silent(uninstall, tmp_path, monkeypatch, capsys):
    """No skills directory and no binary means Codex was never installed — the
    step must not print a header for something that cannot apply."""
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _sweep(uninstall, "codex")
    assert capsys.readouterr().out == ""


def test_the_codex_mcp_removal_ignores_a_config_root_override(uninstall, tmp_path, monkeypatch):
    """Both halves of the sweep must act on the same root. The skills come out
    of the default one, so the MCP command must not inherit an override set
    after installation — that would deregister from a root Tubematic never used
    and leave the real registration behind."""
    _codex_home(uninstall, tmp_path, monkeypatch)
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "elsewhere"))
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: "/b/codex" if n == "codex" else None)
    seen = {}

    def fake_run(cmd, **kw):
        seen["env"] = kw.get("env")
        return __import__("types").SimpleNamespace(returncode=0, stderr="")

    monkeypatch.setattr(uninstall.subprocess, "run", fake_run)
    _answer(uninstall, monkeypatch, True)
    _sweep(uninstall, "codex")
    assert seen["env"] is not None, "the subprocess inherited the ambient environment"
    assert "CODEX_HOME" not in seen["env"]


# ── The sweep must match how the agent was actually installed ───────────────

def _opencode_row(uninstall, monkeypatch, scope, run_path):
    monkeypatch.setattr(uninstall, "_AGENT_ROWS_CACHE",
                        {"opencode": {"scope": scope, "run_path": str(run_path)}})


def test_a_project_scoped_opencode_install_is_swept_from_its_workspace(
        uninstall, tmp_path, monkeypatch):
    """It used to assume user scope for every agent, so a project-scope
    install's skills, commands and MCP entry — all under its workspace — were
    left behind, and the sweep printed no header at all because it found
    nothing in the user directories."""
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    ws = tmp_path / "ws"
    (ws / ".opencode" / "skills" / "tubematic-operator").mkdir(parents=True)
    (ws / ".opencode" / "commands").mkdir(parents=True)
    (ws / ".opencode" / "commands" / "tubematic-status.md").write_text("x")
    (ws / "opencode.json").write_text(
        '{"mcp": {"servers": {"tubematic": {"url": "u"}, "other": {}}}}')
    _opencode_row(uninstall, monkeypatch, "project", ws)
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    assert _sweep(uninstall, "opencode") is True
    assert not (ws / ".opencode" / "skills" / "tubematic-operator").exists()
    assert not (ws / ".opencode" / "commands" / "tubematic-status.md").exists()
    servers = json.loads((ws / "opencode.json").read_text())["mcp"]["servers"]
    assert "tubematic" not in servers and "other" in servers


def test_every_deployed_skill_is_swept_not_just_the_hardcoded_list(
        uninstall, tmp_path, monkeypatch):
    """`_copy_skills` deploys every directory under agent_files/skills, while
    the literal list once fell one behind — a shipped skill was installed by
    every agent and removed by none. Simulated here by dropping a shipped name
    from the literal."""
    monkeypatch.setattr(uninstall, "_TUBEMATIC_SKILLS",
                        [n for n in uninstall._TUBEMATIC_SKILLS if n != "tubematic-operator"])
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    skills = tmp_path / ".config" / "opencode" / "skills"
    (skills / "tubematic-operator").mkdir(parents=True)
    (skills / "somebody-elses-skill").mkdir()
    _opencode_row(uninstall, monkeypatch, "user", tmp_path / "ws")
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    _sweep(uninstall, "opencode")
    assert not (skills / "tubematic-operator").exists()
    assert (skills / "somebody-elses-skill").exists()


def test_a_retired_skill_is_swept_too(uninstall, tmp_path, monkeypatch):
    """An install never upgraded since still holds a skill this release no
    longer ships; uninstalling must not leave it behind."""
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    skills = tmp_path / ".config" / "opencode" / "skills"
    (skills / "tubematic-gif-creator").mkdir(parents=True)
    (skills / "somebody-elses-skill").mkdir()
    _opencode_row(uninstall, monkeypatch, "user", tmp_path / "ws")
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    assert _sweep(uninstall, "opencode") is True
    assert not (skills / "tubematic-gif-creator").exists()
    assert (skills / "somebody-elses-skill").exists()


def test_the_whole_sweep_ignores_a_config_root_override(uninstall, tmp_path, monkeypatch):
    """Not just the skills. Honouring the override on the commands and the MCP
    document while ignoring it for the skills removed the default skills and
    left the default commands and registration exactly where they were."""
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "elsewhere"))
    default = tmp_path / ".config" / "opencode"
    (default / "skills" / "tubematic-operator").mkdir(parents=True)
    (default / "commands").mkdir(parents=True)
    (default / "commands" / "tubematic-status.md").write_text("x")
    (default / "opencode.json").write_text('{"mcp": {"servers": {"tubematic": {"url": "u"}}}}')
    _opencode_row(uninstall, monkeypatch, "user", tmp_path / "ws")
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    _sweep(uninstall, "opencode")
    assert not (default / "skills" / "tubematic-operator").exists()
    assert not (default / "commands" / "tubematic-status.md").exists()
    assert json.loads((default / "opencode.json").read_text())["mcp"]["servers"] == {}


def test_a_jsonc_config_is_found_and_its_comments_survive_removal(
        uninstall, tmp_path, monkeypatch):
    """`opencode mcp add` writes into an existing `.jsonc`, comments and all.
    The entry must be found there AND removed — an uninstaller that leaves the
    registration behind is the thing the sweep exists to prevent — without
    destroying the comments, which reserialising through json.dumps would."""
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    cfg = tmp_path / ".config" / "opencode"
    cfg.mkdir(parents=True)
    (cfg / "opencode.jsonc").write_text(
        '{\n  // mine\n  "model": "anthropic/x",\n'
        '  "mcp": {"servers": {"tubematic": {"url": "u"}, "other": {}}},\n}\n')
    _opencode_row(uninstall, monkeypatch, "user", tmp_path / "ws")
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    assert _sweep(uninstall, "opencode") is True
    text = (cfg / "opencode.jsonc").read_text()
    assert "// mine" in text, "the author's comment was destroyed"
    adapters = uninstall._load_adapters()
    data = adapters["opencode"].parse_config(text)
    assert "tubematic" not in data["mcp"]["servers"], "the registration was left behind"
    assert "other" in data["mcp"]["servers"]
    assert data["model"] == "anthropic/x"


def test_a_document_that_cannot_be_edited_safely_is_left_alone(
        uninstall, tmp_path, monkeypatch, capsys):
    """The text edit is verified before it is written, so a shape the editor
    mis-reads reports the change rather than mangling the file."""
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    cfg = tmp_path / ".config" / "opencode"
    cfg.mkdir(parents=True)
    text = '{"mcp": {"servers": {"tubematic": {"url": "u"}'          # unbalanced
    (cfg / "opencode.json").write_text(text)
    _opencode_row(uninstall, monkeypatch, "user", tmp_path / "ws")
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    _sweep(uninstall, "opencode")
    assert (cfg / "opencode.json").read_text() == text
    assert "by hand" in capsys.readouterr().out


def test_tubematics_own_managed_document_is_removed(uninstall, tmp_path, monkeypatch):
    """It is Tubematic's, inside Tubematic's own workspace."""
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    ws = tmp_path / "ws"
    (ws / ".opencode").mkdir(parents=True)
    managed = ws / ".opencode" / "opencode.json"
    managed.write_text('{"permissions": []}')
    _opencode_row(uninstall, monkeypatch, "user", ws)
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    assert _sweep(uninstall, "opencode") is True
    assert not managed.exists()


def test_the_command_list_covers_every_shipped_command(uninstall):
    # The legacy ~/.claude/commands sweep removes only the stems it names, so a
    # command added to agent_files/ without being added here survived uninstall
    # (four did: tubematic, tubematic-add-topic, tubematic-pause-domain and
    # tubematic-resume-domain).
    repo = Path(__file__).resolve().parents[2]
    shipped = {p.stem for p in (repo / "agent_files" / "claude" / "commands").glob("*.md")}
    assert shipped <= set(uninstall._TUBEMATIC_COMMANDS)


def test_the_user_level_claude_sweep_removes_retired_and_unlisted_skills(
        uninstall, tmp_path, monkeypatch):
    # The Claude path used to read only the literal _TUBEMATIC_SKILLS, so a
    # retired skill (and any shipped one missing from the literal) survived.
    monkeypatch.setattr(uninstall.Path, "home", staticmethod(lambda: tmp_path))
    monkeypatch.setattr(uninstall, "_TUBEMATIC_SKILLS",
                        [n for n in uninstall._TUBEMATIC_SKILLS if n != "tubematic-operator"])
    skills = tmp_path / ".claude" / "skills"
    for name in ("tubematic-gif-creator", "tubematic-operator", "somebody-elses-skill"):
        (skills / name).mkdir(parents=True)
    monkeypatch.setattr(uninstall.shutil, "which", lambda n: None)
    _answer(uninstall, monkeypatch, True)
    uninstall._remove_user_level_integration()
    assert not (skills / "tubematic-gif-creator").exists()
    assert not (skills / "tubematic-operator").exists()
    assert (skills / "somebody-elses-skill").exists()


def test_no_step_number_exceeds_the_total(uninstall):
    # Agent sweeps were numbered 7, 8, ... after Claude's step 6, colliding with
    # the later steps, and the total said 7 while the last step was 9.
    import re
    src = (REPO_ROOT / "uninstall.py").read_text()
    literal = [int(n) for n in re.findall(r"header\(\s*(\d+),", src)]
    assert max(literal) == uninstall.TOTAL_STEPS
    assert "_remove_agent_integration(adapters[name], 6)" in src
