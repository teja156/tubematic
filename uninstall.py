#!/usr/bin/env python3
"""Tubematic uninstall script.

Safely tears down the Tubematic environment on this machine.
Each step is optional and confirmed before anything is deleted.

Run from the repo root:
    python uninstall.py
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()

# Host-side data root — fixed, not configurable (TMDEV-76). Keep in sync with
# docker-compose.yml, onboard/config.py, scripts/config.py.
DATA_ROOT = Path.home() / ".tubematic-data"

TOTAL_STEPS = 9
FORCE = False

# Skill directory names installed by onboard.py
_TUBEMATIC_SKILLS = [
    "tubematic-create-script-writing-skill",
    "tubematic-operator",
    "tubematic-scene-config",
    "tubematic-topic-research",
    "tubematic-script-writing-skill",
    "tubematic-troubleshooting",
]

# Skills an earlier release deployed and this one no longer ships, so an install
# that was never upgraded still holds them. Keep in sync with
# onboard/agent_install.py RETIRED_SKILLS.
_RETIRED_SKILLS = ["tubematic-gif-creator"]

# Command file stems installed by onboard.py. Keep in sync with
# agent_files/claude/commands/ (pinned by scripts/tests/test_uninstall_config.py).
_TUBEMATIC_COMMANDS = [
    "tubematic",
    "tubematic-add-topic",
    "tubematic-pause",
    "tubematic-pause-domain",
    "tubematic-resume-domain",
    "tubematic-resume",
    "tubematic-submit-new-job",
    "tubematic-register-mcp",
    "tubematic-status",
    "tubematic-list-strategies",
    "tubematic-set-strategy",
    "tubematic-dashboard-status",
]


# ── Helpers ────────────────────────────────────────────────────────────────

def ok(msg: str) -> None:
    print(f"  \033[32m✔\033[0m  {msg}")


def info(msg: str) -> None:
    print(f"  \033[34m→\033[0m  {msg}")


def warn(msg: str) -> None:
    print(f"  \033[33m!\033[0m  {msg}")


def skipped(msg: str) -> None:
    print(f"  \033[90m–\033[0m  Skipped: {msg}")


def header(step: int, title: str, description: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  Step {step}/{TOTAL_STEPS}  {title}")
    print(f"{'═' * 60}")
    for line in textwrap.wrap(description, width=56):
        print(f"  {line}")
    print()


def confirm(question: str, default: bool = False) -> bool:
    """Uninstall steps default to NO to avoid accidental data loss."""
    if FORCE:
        print(f"  {question} [forced: yes]")
        return True
    suffix = "[y/N]" if not default else "[Y/n]"
    try:
        answer = input(f"  {question} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    if not answer:
        return default
    return answer in ("y", "yes")


def run_silent(cmd: list[str], cwd: Path = REPO_ROOT) -> bool:
    result = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return result.returncode == 0


def dir_size_mb(path: Path) -> float:
    total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
    return total / (1024 * 1024)


_INSTALL_CONFIG_CACHE: dict[str, str] | None = None
_AGENT_ROWS_CACHE: dict[str, dict] | None = None


def _claude_agent_config(db: Path) -> dict[str, str]:
    """INSTALL_SCOPE / AGENT_RUN_PATH from the claude agents row, or {}."""
    try:
        import sqlite3
        con = sqlite3.connect(str(db))
        try:
            row = con.execute(
                "SELECT install_scope, run_path FROM agents WHERE id = 'claude'"
            ).fetchone()
        finally:
            con.close()
    except Exception:
        # No agents table yet (a pre-TMDEV-90 install) — fall back to settings.
        return {}
    if not row:
        return {}
    out = {}
    if row[0]:
        out["INSTALL_SCOPE"] = row[0]
    if row[1]:
        out["AGENT_RUN_PATH"] = row[1]
    return out


def _agent_rows() -> dict[str, dict]:
    """Every agent's `{id: {scope, run_path}}`, cached like `_install_config`.

    Cached and primed for the same reason: `remove_database()` runs before the
    agent sweep, so the rows have to be read while they still exist. Needed
    because a project-scope agent keeps its skills, its commands and its MCP
    registration under its own workspace — assuming user scope for every agent
    left an entire project-scope install behind, silently, since the sweep
    found nothing in the user directories and printed no header at all.
    """
    global _AGENT_ROWS_CACHE
    if _AGENT_ROWS_CACHE is not None:
        return _AGENT_ROWS_CACHE
    rows: dict[str, dict] = {}
    db = DATA_ROOT / "data" / "tubematic.db"
    if db.exists():
        try:
            import sqlite3
            con = sqlite3.connect(str(db))
            try:
                for aid, scope, run_path in con.execute(
                        "SELECT id, install_scope, run_path FROM agents"):
                    rows[aid] = {"scope": scope or "user", "run_path": run_path or ""}
            finally:
                con.close()
        except Exception:
            # No agents table (a pre-TMDEV-90 install) — every sweep then falls
            # back to user scope, which is what those installs were.
            pass
    _AGENT_ROWS_CACHE = rows
    return rows


def _install_config() -> dict[str, str]:
    """Install configuration, from the settings table (TMDEV-73).

    Keeps the old uppercase key names so the call sites below read the same.

    **Cached on first read, and primed by main() before anything is deleted.**
    The settings table used to be a .env file that step 7 removes, i.e. after
    every consumer had run. It is now the database that step 3 removes, which
    runs *before* remove_claude_integration needs the install scope and agent
    workspace path — so without this cache a confirmed database deletion would
    leave step 5 with nothing to read.
    """
    global _INSTALL_CONFIG_CACHE
    if _INSTALL_CONFIG_CACHE is not None:
        return _INSTALL_CONFIG_CACHE
    mapping = {
        "INSTALL_SCOPE": "install_scope",
        "AGENT_RUN_PATH": "agent_run_path",
        "OUTPUT_VIDEOS_PATH": "output_videos_path",
    }
    env: dict[str, str] = {}
    db = DATA_ROOT / "data" / "tubematic.db"
    if db.exists():
        try:
            import sqlite3
            con = sqlite3.connect(str(db))
            rows = dict(con.execute("SELECT key, value FROM settings").fetchall())
            con.close()
            for upper, row in mapping.items():
                if rows.get(row):
                    env[upper] = rows[row]
            # The Claude agent's scope and workspace live on its agents row
            # (TMDEV-90). The settings rows above only survive on an install
            # that has not re-run --install-agent since upgrading, so the row
            # wins when both exist.
            env.update(_claude_agent_config(db))
        except Exception:
            pass
    _INSTALL_CONFIG_CACHE = env
    return env


# ── Steps ──────────────────────────────────────────────────────────────────

def stop_containers() -> None:
    header(
        1, "Stop & remove containers",
        "Stops the Tubematic containers (renderer + dashboard) and removes them. "
        "This does NOT delete the Docker images — a future 'docker compose up' "
        "will reuse the cached image without rebuilding.",
    )

    result = subprocess.run(
        ["docker", "compose", "ps", "--services", "--filter", "status=running"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    running = [s.strip() for s in result.stdout.splitlines() if s.strip()]

    if not running:
        skipped("No Tubematic containers are running")
    else:
        info(f"Running containers: {', '.join(running)}")
        if confirm("Stop and remove these containers?", default=True):
            run_silent(["docker", "compose", "down"], REPO_ROOT)
            ok("Containers stopped and removed")
        else:
            skipped("Containers left running")


def _compose_volume_names() -> list[str]:
    """Resolve this checkout's actual Docker volume names.

    Compose prefixes each volume key (e.g. "output-videos") with the resolved
    project name (COMPOSE_PROJECT_NAME, or the compose file's directory
    basename by default) — never the literal string "tubematic". Asking
    Compose directly (rather than hardcoding a guessed prefix) keeps this
    correct across checkouts (main repo vs. e2e-testing dev copies) that
    resolve to different project names.
    """
    result = subprocess.run(
        ["docker", "compose", "config", "--format", "json"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    try:
        config = json.loads(result.stdout)
    except (json.JSONDecodeError, ValueError):
        return []
    project = config.get("name", "")
    volume_keys = config.get("volumes", {}).keys()
    return [f"{project}_{key}" for key in volume_keys]


def remove_docker_volumes() -> None:
    header(
        2, "Remove Docker named volumes",
        "Tubematic uses named Docker volumes as bind mounts to the mounted/ directory. "
        "Removing them forces Docker to re-create them on next 'docker compose up'. "
        "The actual data (database, jobs, output videos) lives in mounted/ on your "
        "host — removing volumes here does NOT delete that data.",
    )

    volumes = _compose_volume_names()
    existing = []
    for v in volumes:
        r = subprocess.run(["docker", "volume", "inspect", v], capture_output=True)
        if r.returncode == 0:
            existing.append(v)

    if not existing:
        skipped("No Tubematic Docker volumes found")
        return

    info(f"Found volumes: {', '.join(existing)}")
    if confirm("Remove these Docker volumes? (host data in mounted/ is unaffected)", default=True):
        for v in existing:
            run_silent(["docker", "volume", "rm", v])
        ok(f"Removed {len(existing)} volume(s)")
    else:
        skipped("Docker volumes kept")


def remove_database() -> None:
    header(
        3, "Remove database",
        "The SQLite database at ~/.tubematic-data/data/tubematic.db stores all pipeline state: "
        "projects, videos, comments, cost tracking, and the polling cursor. "
        "Deleting it gives you a clean slate. Your rendered mp4s and job assets are "
        "NOT affected — only the metadata is removed.",
    )

    db_path = DATA_ROOT / "data" / "tubematic.db"
    if not db_path.exists():
        skipped("No database found at ~/.tubematic-data/data/tubematic.db")
        return

    size_kb = db_path.stat().st_size // 1024
    info(f"Database: ~/.tubematic-data/data/tubematic.db ({size_kb}KB)")
    if confirm("Delete the database? This removes ALL pipeline state permanently.", default=False):
        db_path.unlink()
        ok("Database deleted")
    else:
        skipped("Database kept")


def remove_job_files() -> None:
    header(
        4, "Remove job working files",
        "~/.tubematic-data/jobs/ contains per-video working files: audio.mp3, timeline.json, "
        "and scene-config.json for each job. These are working files only — the final "
        "rendered mp4s are in ~/.tubematic-data/output_videos/ and are NOT touched here. "
        "Removing job files frees disk space but means you'd need to re-run ElevenLabs "
        "to re-render any video.",
    )

    jobs_dir = DATA_ROOT / "jobs"
    job_dirs = [d for d in jobs_dir.iterdir() if d.is_dir()] if jobs_dir.exists() else []

    if not job_dirs:
        skipped("No job directories found in ~/.tubematic-data/jobs/")
        return

    total_mb = dir_size_mb(jobs_dir)
    info(f"Found {len(job_dirs)} job director{'y' if len(job_dirs) == 1 else 'ies'} ({total_mb:.1f}MB total)")

    if confirm(f"Delete all {len(job_dirs)} job director{'y' if len(job_dirs) == 1 else 'ies'}?", default=False):
        for d in job_dirs:
            shutil.rmtree(d, ignore_errors=True)
        ok(f"Deleted {len(job_dirs)} job director{'y' if len(job_dirs) == 1 else 'ies'} ({total_mb:.1f}MB freed)")
    else:
        skipped("Job files kept")


def remove_scenes() -> None:
    header(
        5, "Remove generated scenes",
        "~/.tubematic-data/scenes/generated/ holds the scene .tsx files the agent wrote, "
        "namespaced per video. They are regenerated from the script on the next render, so "
        "removing them costs nothing but agent time — but a video you might revise later "
        "would have to have its scenes re-authored from scratch.",
    )

    scenes_dir = DATA_ROOT / "scenes" / "generated"
    entries = [d for d in scenes_dir.iterdir()] if scenes_dir.exists() else []

    if not entries:
        skipped("No generated scenes found in ~/.tubematic-data/scenes/generated/")
        return

    total_mb = dir_size_mb(scenes_dir)
    info(f"Found {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} ({total_mb:.1f}MB total)")

    if confirm(f"Delete all {len(entries)} generated scene entr{'y' if len(entries) == 1 else 'ies'}?", default=False):
        for d in entries:
            shutil.rmtree(d, ignore_errors=True) if d.is_dir() else d.unlink(missing_ok=True)
        ok(f"Deleted {len(entries)} entr{'y' if len(entries) == 1 else 'ies'} ({total_mb:.1f}MB freed)")
    else:
        skipped("Generated scenes kept")


def remove_claude_integration() -> None:
    """Remove skills, commands, MCP, and (if project-level) the agent workspace."""
    env = _install_config()
    scope = env.get("INSTALL_SCOPE", "")

    if not scope:
        # No settings row (a pre-migration install, or the DB was already gone
        # when main() primed the cache) — ask. `confirm()` handles EOF for its
        # own prompts; this one has to do it too, or a piped --force run dies
        # with a traceback instead of falling back.
        print()
        print("  Could not detect install scope.")
        if FORCE:
            print("  --force: assuming user-level install.")
            scope = "user"
        else:
            try:
                raw = input("  Was this installed at user level or project level? "
                            "[user/project]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                print()
                raw = ""
            scope = raw if raw in ("user", "project") else "user"

    if scope == "user":
        _remove_user_level_integration()
    else:
        _remove_project_level_integration(env)
    # Every other agent keeps its files somewhere else entirely, so each is
    # swept regardless of the scope answered above. Silent and skipped for an
    # agent that was never installed.
    _remove_other_agent_integrations()


def _load_adapters() -> dict:
    """scripts/agent_adapters.py, loaded by path (it ships beside this file).

    Any failure yields {} and the sweep below is skipped with a warning rather
    than aborting the uninstall — the Claude paths above do not depend on it.
    """
    import importlib.util
    # Resolved from this file's own location rather than from REPO_ROOT: the
    # adapters ship beside uninstall.py in both the checkout and the release
    # tarball, and this must not move when a caller repoints REPO_ROOT.
    path = Path(__file__).resolve().parent / "scripts" / "agent_adapters.py"
    try:
        spec = importlib.util.spec_from_file_location("tubematic_agent_adapters", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module.ADAPTERS
    except Exception:
        return {}


def _remove_other_agent_integrations() -> None:
    """Remove Tubematic's files and MCP registration for every non-Claude agent.

    Claude keeps the scope-branching path above; the others are swept here
    regardless of the scope answered for Claude, because each keeps its files
    somewhere else entirely and an agent that was never installed simply has
    nothing to find. Driven off the adapters rather than a hand-written copy
    per agent: a fourth agent must not be able to ship with an uninstaller that
    silently leaves it behind, which is exactly what happened when Codex was
    added.
    """
    adapters = _load_adapters()
    if not adapters:
        warn("Could not read scripts/agent_adapters.py — non-Claude agent files not swept")
        return
    # Every agent's sweep is part of step 6, beside Claude's: numbering them
    # 7, 8, ... collided with the cron, .env and data-root steps that follow.
    for name in sorted(adapters):
        if name == "claude":
            continue
        _remove_agent_integration(adapters[name], 6)


def _deployed_skill_names() -> list:
    """Every skill directory this checkout ships, for the sweep to look for.

    Read from `agent_files/skills/` rather than from `_TUBEMATIC_SKILLS`,
    because `_copy_skills` deploys **every** directory there while that literal
    list once fell one behind (a shipped skill was installed by every agent and
    swept by none). The literal stays as a floor so a tree without
    `agent_files/` still removes the names we know about, and `_RETIRED_SKILLS`
    covers what an older release deployed and this one no longer ships.
    """
    root = Path(__file__).resolve().parent / "agent_files" / "skills"
    names = set(_TUBEMATIC_SKILLS) | set(_RETIRED_SKILLS)
    if root.is_dir():
        names |= {d.name for d in root.iterdir() if d.is_dir()}
    return sorted(names)


def _remove_agent_integration(adapter, step: int) -> bool:
    """One agent's sweep, at the scope that agent was actually installed at.

    Returns whether anything was printed.
    """
    home = Path.home()
    row = _agent_rows().get(adapter.name, {})
    scope = row.get("scope") or "user"
    if scope not in adapter.SUPPORTED_SCOPES:
        scope = adapter.SUPPORTED_SCOPES[0]
    # The installer's default when the row is gone or predates agent rows —
    # `onboard/agent_install.py::default_run_path`. Keep in sync.
    default_ws = Path.home() / ".tubematic-agent" / adapter.name
    workspace = Path(row.get("run_path") or default_ws).expanduser()

    if scope == "project":
        skills_dir = adapter.project_skills_dir(workspace)
        commands_dir = adapter.project_commands_dir(workspace) if adapter.HAS_COMMANDS else None
    else:
        # respect_override=False deliberately, on EVERY path that can name a
        # root: the directories to clean are the ones a SCHEDULED run uses, and
        # cron never inherits an environment override. Honouring one on some
        # paths and not others is worse than either — it removed the default
        # skills while leaving the default commands and MCP registration
        # exactly where they were.
        skills_dir = adapter.user_skills_dir(home, respect_override=False)
        commands_dir = adapter.user_commands_dir(home, respect_override=False) \
            if adapter.HAS_COMMANDS else None

    managed = adapter.managed_config_file(workspace) \
        if hasattr(adapter, "managed_config_file") else None
    present = [n for n in _deployed_skill_names() if (skills_dir / n).exists()] \
        if skills_dir.is_dir() else []
    commands = sorted(f.name for f in commands_dir.glob("tubematic*.md")) \
        if commands_dir and commands_dir.is_dir() else []
    binary = shutil.which(adapter.binary_name)
    config = adapter.mcp_config_file(home, workspace, scope, False) \
        if hasattr(adapter, "mcp_config_file") else None
    has_entry = config is not None and _config_names_tubematic(adapter, config)
    if not present and not commands and not has_entry and not binary \
            and not (managed and managed.is_file()):
        return False

    label = adapter.display_name
    header(step, f"Remove {label} integration",
           f"Removes Tubematic skills and commands from {skills_dir.parent}/ and deregisters "
           f"the tubematic MCP server from {label} ({scope} scope). Only Tubematic-specific "
           f"files are removed.")

    _remove_named(present, skills_dir, "skill", label)
    if adapter.HAS_COMMANDS:
        _remove_named(commands, commands_dir, "command", label)
    if managed and managed.is_file():
        # Tubematic's own document, inside Tubematic's own workspace.
        if confirm(f"Remove Tubematic's {label} config ({managed})?", default=True):
            managed.unlink(missing_ok=True)
            ok(f"Removed {managed}")
        else:
            skipped(f"{label} managed config kept")

    remove_argv = adapter.mcp_remove_argv(adapter.binary_name, scope)
    if remove_argv is None:
        # This agent has no deregistration command at all, so the entry its
        # `mcp add` wrote is removed from the config document instead. Doing it
        # here rather than inventing an argv is what keeps an uninstall from
        # reporting success for a command that was never run.
        _remove_mcp_entry_from_config(adapter, config, label)
        return True
    if not binary:
        warn(f"'{adapter.binary_name}' binary not found — MCP server not deregistered")
        warn(f"Remove manually: {' '.join(remove_argv)}")
        return True
    # Strip the agent's own config-root override for the same reason the roots
    # above ignore it: deregistering from a root Tubematic never used would
    # leave the real registration in place while reporting success.
    env = {k: v for k, v in os.environ.items() if k != (adapter.CONFIG_HOME_ENV or "")}
    cwd = workspace if scope == "project" and workspace.is_dir() else REPO_ROOT
    if confirm(f"Deregister the tubematic MCP server from {label}?", default=True):
        r = subprocess.run(adapter.mcp_remove_argv(binary, scope),
                           capture_output=True, text=True, cwd=cwd, env=env)
        if r.returncode == 0:
            ok(f"tubematic MCP server deregistered from {label}")
        else:
            warn(f"MCP remove failed: {(r.stderr or '').strip()}")
            warn(f"Remove manually: {' '.join(remove_argv)}")
    else:
        skipped(f"{label} MCP server kept")
    return True


def _remove_named(names: list, directory, kind: str, label: str) -> None:
    if not names:
        skipped(f"No Tubematic {kind}s found for {label}")
        return
    info(f"Tubematic {kind}s in {directory}/: {', '.join(names)}")
    if not confirm(f"Remove {len(names)} Tubematic {kind}(s) from {directory}/?", default=True):
        skipped(f"{label} {kind}s kept")
        return
    for name in names:
        target = directory / name
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        else:
            target.unlink(missing_ok=True)
    ok(f"Removed {len(names)} {kind}(s) from {directory}/")


def _config_names_tubematic(adapter, path: Path) -> bool:
    """Whether this document registers the tubematic MCP server.

    A document that exists but will not parse falls back to looking for the
    name in the raw text. Answering "no" there would skip the whole agent in
    silence — no header, no warning — on exactly the file a human most needs
    told about. A false positive costs a printed instruction; a false negative
    leaves the registration behind without saying so.
    """
    try:
        text = path.read_text()
    except OSError:
        return False
    try:
        data = adapter.parse_config(text)
    except Exception:
        return '"tubematic"' in text
    servers = ((data or {}).get("mcp") or {}).get("servers")
    return isinstance(servers, dict) and "tubematic" in servers


def _remove_mcp_entry_from_config(adapter, path, label: str) -> None:
    """Drop only `mcp.servers.tubematic` from an agent's config document.

    Only that one key: the file is the operator's own agent configuration and
    everything else in it belongs to them. The edit is made on the TEXT, so
    comments survive — reserialising through `json.dumps` would delete them,
    and refusing to edit at all is what used to leave an uninstalled agent's
    server still registered. The edit is verified before it is written, so a
    document the editor cannot read is reported instead of mangled.
    """
    if path is None or not _config_names_tubematic(adapter, path):
        skipped(f"No tubematic MCP entry found for {label}")
        return
    if not confirm(f"Deregister the tubematic MCP server from {label} ({path})?", default=True):
        skipped(f"{label} MCP server kept")
        return
    try:
        edited = adapter.remove_mcp_entry(path.read_text())
    except Exception:
        edited = None
    if edited is None:
        warn(f"Could not safely edit {path} — it was left unchanged")
        warn('Remove the "tubematic" entry under mcp.servers by hand')
        return
    path.write_text(edited)
    ok(f"tubematic MCP server deregistered from {label}")


def _remove_user_level_integration() -> None:
    header(
        6, "Remove user-level Claude integration",
        "Removes Tubematic skills and commands from ~/.claude/, "
        "and deregisters the tubematic MCP server from user scope. "
        "Only Tubematic-specific files are removed — other skills/commands are untouched.",
    )

    claude_dir = Path.home() / ".claude"

    # Skills
    skills_dir = claude_dir / "skills"
    removed_skills = []
    if skills_dir.is_dir():
        # Every shipped skill plus the retired ones, as for the other agents --
        # the literal list alone left a skill behind once.
        for name in _deployed_skill_names():
            p = skills_dir / name
            if p.exists():
                removed_skills.append(name)

    if removed_skills:
        info(f"Tubematic skills in ~/.claude/skills/: {', '.join(removed_skills)}")
        if confirm(f"Remove {len(removed_skills)} Tubematic skill(s) from ~/.claude/skills/?", default=True):
            for name in removed_skills:
                shutil.rmtree(skills_dir / name, ignore_errors=True)
            ok(f"Removed {len(removed_skills)} skill(s)")
        else:
            skipped("Skills kept")
    else:
        skipped("No Tubematic skills found in ~/.claude/skills/")

    # Commands
    cmds_dir = claude_dir / "commands"
    removed_cmds = []
    if cmds_dir.is_dir():
        for stem in _TUBEMATIC_COMMANDS:
            p = cmds_dir / f"{stem}.md"
            if p.exists():
                removed_cmds.append(p)

    if removed_cmds:
        info(f"Tubematic commands in ~/.claude/commands/: {len(removed_cmds)} file(s)")
        if confirm(f"Remove {len(removed_cmds)} Tubematic command file(s) from ~/.claude/commands/?", default=True):
            for p in removed_cmds:
                p.unlink()
            ok(f"Removed {len(removed_cmds)} command file(s)")
        else:
            skipped("Commands kept")
    else:
        skipped("No Tubematic commands found in ~/.claude/commands/")

    # MCP
    claude_bin = shutil.which("claude")
    if claude_bin:
        if confirm("Deregister the tubematic MCP server (user scope)?", default=True):
            r = subprocess.run(
                [claude_bin, "mcp", "remove", "--scope", "user", "tubematic"],
                capture_output=True, text=True,
            )
            if r.returncode == 0:
                ok("tubematic MCP server deregistered (user scope)")
            else:
                warn(f"MCP remove failed: {r.stderr.strip()}")
                warn("Remove manually: claude mcp remove --scope user tubematic")
        else:
            skipped("MCP server kept")
    else:
        warn("'claude' binary not found — MCP server not deregistered")
        warn("Remove manually: claude mcp remove --scope user tubematic")


def _remove_project_level_integration(env: dict) -> None:
    workspace_str = env.get("AGENT_RUN_PATH", "")
    workspace = Path(workspace_str).expanduser().resolve() if workspace_str else None

    header(
        6, "Remove agent workspace",
        f"Removes the dedicated agent workspace directory "
        f"({workspace or 'AGENT_RUN_PATH not set'}). "
        "This contains skills, commands, CLAUDE.md, and the MCP registration for the agent. "
        "Your rendered videos and pipeline database are NOT affected.",
    )

    if not workspace:
        skipped("Agent workspace path not recorded — nothing to remove")
        return

    if not workspace.exists():
        skipped(f"Workspace directory not found: {workspace}")
        return

    total_mb = dir_size_mb(workspace)
    info(f"Workspace: {workspace} ({total_mb:.1f}MB)")

    if confirm(f"Delete agent workspace at {workspace}?", default=False):
        shutil.rmtree(workspace, ignore_errors=True)
        ok(f"Deleted: {workspace}")
    else:
        skipped("Agent workspace kept")

    # Deregister MCP (project scope)
    claude_bin = shutil.which("claude")
    if claude_bin:
        if confirm("Deregister the tubematic MCP server (project scope)?", default=True):
            r = subprocess.run(
                [claude_bin, "mcp", "remove", "tubematic"],
                capture_output=True, text=True, cwd=REPO_ROOT,
            )
            if r.returncode == 0:
                ok("tubematic MCP server deregistered (project scope)")
            else:
                warn(f"MCP remove failed: {r.stderr.strip()}")
                warn("Remove manually: claude mcp remove tubematic")
        else:
            skipped("MCP server kept")
    else:
        warn("'claude' binary not found — MCP server not deregistered")
        warn("Remove manually: claude mcp remove tubematic")


def remove_cron() -> None:
    header(
        7, "Cron jobs",
        "Removes the two Tubematic cron entries added by onboard.py: "
        "the pipeline poll and the daily research run. "
        "Other cron entries on your system are untouched.",
    )
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        skipped("No crontab found")
        return

    existing = result.stdout.splitlines()
    tubematic_lines = [l for l in existing if "poll.py" in l or "# Tubematic" in l]

    if not tubematic_lines:
        skipped("No Tubematic cron entries found")
        return

    info(f"Found {len(tubematic_lines)} Tubematic cron line(s)")
    for l in tubematic_lines:
        print(f"    {l}")

    if confirm("Remove these cron entries?", default=True):
        filtered = [l for l in existing if "poll.py" not in l and "# Tubematic" not in l]
        subprocess.run(
            ["crontab", "-"],
            input="\n".join(filtered) + "\n",
            text=True,
            check=True,
        )
        ok("Tubematic cron entries removed")
    else:
        skipped("Cron entries kept")


def remove_env() -> None:
    header(
        8, "Generated files and .env leftovers",
        "docker-compose.override.yml is generated by onboard.py. A .env file, if one is "
        "still present, pre-dates this version and is no longer read at runtime — but it "
        "does still contain your API keys in plaintext. Neither is committed; both exist "
        "only on this machine.\n"
        "Your keys now live in the pipeline database, which step 6 covers.",
    )

    override = REPO_ROOT / "docker-compose.override.yml"
    if override.exists():
        if confirm("Delete docker-compose.override.yml?", default=True):
            override.unlink()
            ok("docker-compose.override.yml deleted")
        else:
            skipped("docker-compose.override.yml kept")
    else:
        skipped("No docker-compose.override.yml found")

    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        skipped("No .env file found")
        return

    if confirm("Delete the leftover .env? It still holds API keys in plaintext.", default=False):
        env_path.unlink()
        ok(".env deleted")
    else:
        skipped(".env kept")


def remove_data_root() -> None:
    header(
        9, "Pipeline data root",
        "~/.tubematic-data/ is where every bind mount lives. Since it sits outside the git "
        "checkout, deleting the repository no longer removes it — nothing does, unless you "
        "say so here. The earlier steps clear the database, job files and generated scenes "
        "individually; what is usually left is your rendered videos.",
    )

    if not DATA_ROOT.exists():
        skipped(f"No data root at {DATA_ROOT}")
        return

    videos_dir = DATA_ROOT / "output_videos"
    videos = [f for f in videos_dir.rglob("*.mp4")] if videos_dir.exists() else []
    total_mb = dir_size_mb(DATA_ROOT)
    info(f"{DATA_ROOT} holds {total_mb:.1f}MB"
          + (f", including {len(videos)} rendered video{'' if len(videos) == 1 else 's'}" if videos else ""))

    # Named in the prompt rather than buried in the header: this is the one
    # irreversible thing the script can do, and the videos are the product.
    question = (
        f"Delete {DATA_ROOT} entirely, INCLUDING {len(videos)} rendered video"
        f"{'' if len(videos) == 1 else 's'}?"
        if videos else f"Delete {DATA_ROOT} entirely?"
    )
    if confirm(question, default=False):
        shutil.rmtree(DATA_ROOT, ignore_errors=True)
        ok(f"Deleted {DATA_ROOT} ({total_mb:.1f}MB freed)")
        return

    # Declined: prune what is provably empty so the leftovers are only the
    # things actually worth keeping, and say where they are.
    pruned = []
    for sub in ("data", "jobs", "output_videos", "logs", "scenes/generated", "scenes"):
        d = DATA_ROOT / sub
        try:
            if d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                pruned.append(sub)
        except OSError:
            pass
    if pruned:
        info(f"Removed {len(pruned)} empty director{'y' if len(pruned) == 1 else 'ies'}: {', '.join(pruned)}")
    if (DATA_ROOT / "secrets").is_dir():
        # Credentials, so named on their own rather than left inside "remaining
        # content". A reinstall makes new ones, so they are safe to delete.
        info(f"The service tokens are still in {DATA_ROOT / 'secrets'} — a reinstall creates "
             f"new ones, so they can go: rm -rf {DATA_ROOT / 'secrets'}")
    skipped(f"Data root kept — remaining content is under {DATA_ROOT}")


def print_summary() -> None:
    print(f"\n{'═' * 60}")
    print("  Uninstall complete")
    print(f"{'═' * 60}")
    print(textwrap.dedent("""
  To reinstall from scratch:
    python onboard.py

  Anything you chose to keep is under ~/.tubematic-data/ — rendered videos
  in output_videos/, plus whatever else you declined to delete. That
  directory sits outside the git checkout, so removing the repository will
  NOT remove it; delete it by hand when you no longer want the videos.
    """))


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    global FORCE
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--force", "--yes", "-y", action="store_true")
    args, _ = parser.parse_known_args()
    FORCE = args.force

    print("\n" + "═" * 60)
    print("  Tubematic — Uninstall")
    if FORCE:
        print("  Running in --force mode: all steps auto-confirmed.")
    else:
        print("  Each step will ask for confirmation before deleting anything.")
        print("  All prompts default to NO to prevent accidental data loss.")
    print("═" * 60)

    if not FORCE:
        try:
            input("\n  Press Enter to begin, or Ctrl+C to cancel...")
        except (EOFError, KeyboardInterrupt):
            print("\n  Cancelled.")
            sys.exit(0)

    # Read install config while the database still exists — remove_database()
    # is three lines below, and remove_claude_integration() needs the scope
    # and workspace path it holds. The agent rows go the same way: the sweep
    # for every non-Claude agent needs each one's own scope and workspace.
    _install_config()
    _agent_rows()

    stop_containers()
    remove_docker_volumes()
    remove_database()
    remove_job_files()
    remove_scenes()
    remove_claude_integration()
    remove_cron()
    remove_env()
    remove_data_root()
    print_summary()


if __name__ == "__main__":
    main()
