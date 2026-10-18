"""`python onboard.py --install-agent <name>` — install one agent (TMDEV-90).

The main wizard sets up the project only; agents are installed here, one at a
time. Re-running this for an installed agent is the update path, and the
redeploy path: every question is pre-filled from the agent's row, and the
skills and commands are copied again from this checkout — so after skills
change, re-running it (inside the container, for a Kasm install) is the whole
redeploy.

In order: preconditions (a database to write into, the binary, a logged-in
CLI), the questions (install scope, workspace, wipe, models, effort), then the
deploy and the agents row. Every model is probed against the installed CLI
before it is stored, so the dashboard can offer the list as-is and the API can
reject anything outside it.

The row is written straight into sqlite, never over HTTP: the API rejects
model-list writes on purpose (no container has an agent binary to validate
against), and Flask may not even be running yet on a fresh install.
"""
import importlib.util
import json
import shlex
import shutil
import subprocess
import sys
import tempfile
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from onboard import api_keys
from onboard.actions import (
    _copy_commands, _copy_skills, _ensure_db_writable, _install_remotion_skills,
    _patch_mcp_header_helper, _read_agent_config, _register_mcp, _write_agent_allowlist,
    _write_agent_permissions, describe_existing_workspace,
)
from onboard.config import (
    DB_PATH, POLL_LOG_DIR, REPO_ROOT, Field, OnboardConfig, agent_workspace_exists, read_agents,
    read_settings, writable_parent,
)
from onboard.executor import Executor


# Skills an earlier release deployed and this one no longer ships. `_copy_skills`
# only ever adds, so without this sweep an upgraded install would keep a skill
# that teaches the agent a tool the server no longer has. Keep in sync with
# uninstall.py's _RETIRED_SKILLS (that script runs standalone).
RETIRED_SKILLS = ("tubematic-gif-creator",)


def _sweep_retired_skills(skills_dir: Path, *, ex: Executor, rep) -> None:
    """Remove the retired skills from one skills root, and nothing else."""
    found = [skills_dir / n for n in RETIRED_SKILLS
             if (skills_dir / n).is_symlink() or (skills_dir / n).is_dir()]
    for path in found:
        (ex.unlink if path.is_symlink() else ex.rmtree)(path)
    if found:
        rep.ok(f"Retired skills removed from {skills_dir}/: {', '.join(p.name for p in found)}")


def _load_adapters() -> dict:
    """scripts/agent_adapters.py, loaded by path.

    One home for each agent's argv shapes and output markers, shared with
    poll.py. Loaded by path rather than by putting scripts/ on sys.path: that
    directory has its own config.py, which would shadow nothing today but
    would be one bare `import config` away from doing so.
    """
    path = REPO_ROOT / "scripts" / "agent_adapters.py"
    global _ADAPTER_MODULE
    spec = importlib.util.spec_from_file_location("tubematic_agent_adapters", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _ADAPTER_MODULE = module
    return module.ADAPTERS


_ADAPTER_MODULE = None
ADAPTERS = _load_adapters()


def mcp_auth():
    """How every agent CLI authenticates to the MCP server (TMDEV-152).

    The helper is this install's own interpreter running this install's
    scripts/mcp_auth_header.py, so the registration names the install
    directory: upgrade.py re-registers from the new one, and a hand-moved
    install must re-run --install-agent. Neither field is the token itself.
    """
    from tubematic_core.auth import HOST_SECRETS_DIR
    script = REPO_ROOT / "scripts" / "mcp_auth_header.py"
    return _ADAPTER_MODULE.McpAuth(
        helper=f"{shlex.quote(sys.executable)} {shlex.quote(str(script))}",
        token_file=str(HOST_SECRETS_DIR / "mcp_token"),
    )

# `claude auth status` is local and quick; a model probe is a real (tiny) run.
AUTH_TIMEOUT_SECS = 30
PROBE_TIMEOUT_SECS = 120


def managed_config_siblings(adapter, workspace) -> list:
    """Every config document OpenCode would load from the managed directory.

    Not just the one Tubematic writes: the sibling basenames are loaded too,
    and a later one outranks an earlier one, so a rule in any of them can
    override every rule in ours.
    """
    managed = getattr(adapter, "managed_config_files", None)
    if managed is None:
        return []
    return list(managed(workspace))


def default_run_path(name: str) -> str:
    """~/.tubematic-agent/<agent>/: one directory per agent, beside the shared
    logs/ directory (POLL_LOG_DIR), so wiping or uninstalling one agent can
    never reach another agent's files or the poll logs."""
    return str(POLL_LOG_DIR.parent / name)


def workspace_conflict(val: str, agent_id: str, db_path: Path = None, *,
                       include_config: bool = True) -> str | None:
    """Why `val` cannot be `agent_id`'s workspace, or None.

    It must not be, contain, or sit inside the poll logs directory or another
    agent's workspace (uninstalled agents included — a re-install reuses the
    path). The workspace is the agent's cwd and the unit a wipe deletes, so any
    overlap would expose, or delete, something that belongs to someone else.
    """
    if not val:
        return None
    path = Path(val).expanduser().resolve()

    def overlaps(other: Path) -> bool:
        return path == other or other in path.parents or path in other.parents

    # An agent whose config Tubematic writes takes the workspace's config
    # document for its own — it is written on install and removed on uninstall.
    # That is safe because the workspace is Tubematic's own directory, so the
    # one case worth refusing is a directory that is ALREADY somebody's
    # OpenCode project. Caught here, at the question, rather than by a check
    # further in: this runs before anything is copied or registered, on every
    # path that asks the question, and needs no gate of its own.
    #
    # EXEMPT this agent's own recorded workspace, or the rule eats itself: a
    # successful install creates exactly the file the rule rejects, so a
    # re-install is refused, `current_values` silently falls back to the
    # default path, and `upgrade.py` then deploys somewhere the agents row does
    # not point at. The row is the authority on which directory is already
    # ours — no need to inspect the file to find out.
    adapter = ADAPTERS.get(agent_id)
    # A LIVE row only. An archived one means the agent was uninstalled: its
    # config was deleted and its workspace deliberately kept, so a document at
    # that path now is the operator's. Counting archived rows let a re-install
    # exempt and rewrite it, and a full uninstall delete it as Tubematic's.
    existing = next((a for a in read_agents(db_path or DB_PATH)
                     if a["id"] == agent_id and not a.get("archived_at")), None)
    own = Path(existing["run_path"]).expanduser().resolve() \
        if existing and existing.get("run_path") else None
    if adapter is not None and include_config:
        # BOTH basenames: OpenCode loads `.opencode/opencode.jsonc` after
        # `.opencode/opencode.json`, so checking only the one Tubematic writes
        # leaves a sibling that silently outranks every rule in it. Measured —
        # an operator `.jsonc` beside our `.json` turned a credential deny back
        # into an allow and the agent read the file.
        #
        # The exemption is ONE FILE, not the directory: Tubematic's own
        # document, in the workspace the agents row already records. Exempting
        # the whole directory let a sibling dropped in afterwards survive a
        # re-install and an upgrade, still outranking the denies while the
        # install reported success — the checklist would warn, but only after.
        ours = set(adapter.managed_config_files(path)) if hasattr(
            adapter, "managed_config_files") else set()
        for foreign in managed_config_siblings(adapter, path):
            if foreign in ours and path == own:
                continue                      # our document, in our workspace
            if not foreign.exists():
                continue
            if path == own:
                # Its own workspace, with a document somebody added beside
                # ours. Relocating the agent is the wrong advice here — the
                # file is the thing to remove.
                return (f"{foreign} sits beside Tubematic's own config in this agent's "
                        f"workspace and is loaded after it, so its rules override Tubematic's "
                        f"— remove it, or give the agent a different workspace")
            return (f"{val} already contains an OpenCode config ({foreign}). The agent "
                    f"workspace is Tubematic's own directory and that file would be "
                    f"overwritten, removed, or silently override Tubematic's rules — pick a "
                    f"directory of its own, e.g. {default_run_path(agent_id)}")

    logs = POLL_LOG_DIR.expanduser().resolve()
    if overlaps(logs):
        return (f"{val} overlaps the poll logs directory ({logs}) — pick a directory of its "
                f"own, e.g. {default_run_path(agent_id)}")
    for agent in read_agents(db_path or DB_PATH):
        if agent["id"] == agent_id or not agent.get("run_path"):
            continue
        other = Path(agent["run_path"]).expanduser().resolve()
        if overlaps(other):
            return (f"{val} overlaps agent '{agent['id']}''s workspace ({other}) — every agent "
                    f"needs a directory of its own, e.g. {default_run_path(agent_id)}")
    return None

# Keep in sync with tubematic_core/migrations/. This second copy exists because
# this is the only writer of agent rows and runs on the host, where the API's
# schema code is not importable (and Flask may not have started yet).
# onboard/tests/test_agent_install.py pins it against a REAL, fully migrated
# database rather than against any migration's source text — read that test's
# docstring before changing either.
AGENTS_SCHEMA = """
    CREATE TABLE IF NOT EXISTS agents (
        id            TEXT PRIMARY KEY,
        name          TEXT NOT NULL,
        binary        TEXT NOT NULL,
        run_path      TEXT NOT NULL,
        install_scope TEXT NOT NULL DEFAULT 'user',
        models        TEXT NOT NULL DEFAULT '[]',
        is_default    INTEGER NOT NULL DEFAULT 0,
        weight        INTEGER NOT NULL DEFAULT 1,
        verified_at   TEXT NOT NULL DEFAULT '',
        archived_at   TEXT,
        created_at    TEXT NOT NULL,
        updated_at    TEXT NOT NULL,
        -- Column ORDER matters, not just the set: the sync test compares
        -- PRAGMA table_info rows, cid included. A migrated database grows a
        -- column by ALTER TABLE ADD COLUMN, which always appends — so every
        -- column added after the baseline belongs at the bottom here, in
        -- migration order, however oddly it reads next to the timestamps.
        effort        TEXT NOT NULL DEFAULT 'high'
    )
"""

# Written by the pre-agents main flow. Read once, as the pre-fill for an
# upgrade's first --install-agent, then deleted: the agents row replaces them.
LEGACY_SETTING_ROWS = ("agent_binary", "agent_run_path", "install_scope")

SCOPE_FIELD = Field(
    "INSTALL_SCOPE", "Install at", kind="select", choices=["user", "project"], default="user",
    help="user: skills and commands go to ~/.claude/, so they are available in every Claude "
         "Code session (recommended). project: they go only into this agent's workspace.")

RUN_PATH_FIELD = Field(
    "AGENT_RUN_PATH", "Agent workspace path", default=default_run_path("claude"),
    validator=writable_parent,
    help="Cron runs this agent from here, never from the repo root, so it only reaches the "
         "pipeline through its tools. Each agent needs a directory of its own, separate from "
         "every other agent's and from the shared poll logs.")


def scope_field(adapter) -> Field:
    """SCOPE_FIELD narrowed to the scopes this agent can actually honour."""
    return replace(SCOPE_FIELD, choices=list(adapter.SUPPORTED_SCOPES))


def run_path_field(name: str) -> Field:
    """RUN_PATH_FIELD for one agent: its own default, and a check that the
    path overlaps neither the poll logs nor another agent's workspace."""
    return replace(RUN_PATH_FIELD, default=default_run_path(name),
                   validator=lambda v: writable_parent(v) or workspace_conflict(v, name))

WIPE_FIELD = Field(
    "WIPE_AGENT_WORKSPACE", "Wipe the existing agent workspace and start fresh?",
    source="ephemeral", kind="select", choices=["false", "true"], default="false",
    condition=agent_workspace_exists,
    help="Only asked because the workspace above already exists from a prior install. "
         "Keeping it is the normal choice for a redeploy — skills and commands are overwritten "
         "in place either way.")


def models_field(adapter, suggestions: list, probe) -> Field:
    """The model-list question, built per install: its suggestions come from
    the binary actually installed, and its check probes that binary.

    The alias/full-ID tradeoff is only explained for an agent that HAS aliases.
    Codex has none — its models are catalog slugs — so telling a Codex user
    about `opus` and `claude-opus-5` describes names their CLI would reject.
    """
    choices = list(adapter.ALIASES) + [m for m in suggestions if m not in adapter.ALIASES]
    help_text = ("The models videos may run with. The first is this agent's default, and the "
                 "dashboard offers exactly this list. Each is checked against the installed CLI "
                 "before it is kept. ")
    if adapter.ALIASES:
        help_text += (f"An alias ({', '.join(adapter.ALIASES)}) always means the current model of "
                      "that family — the stored name never changes, but the model behind it does, "
                      "so you cannot later tell which model made a video. A full ID is "
                      "reproducible but will eventually be retired. ")
    help_text += "Re-run this command after upgrading the CLI to re-check the list."
    return Field(
        "AGENT_MODELS", "Models", kind="models", required=True, default="[]",
        dynamic_choices=lambda _values: choices, key_check=probe, help=help_text)


def effort_field(adapter) -> Field:
    """The effort-level question (TMDEV-106).

    `advanced`, so the minimal questionnaire never asks it and the install ends
    at the adapter's default — rule 2 from the ticket. Note that run_install_agent
    has to filter on that attribute itself: unlike the main wizard, this flow
    builds its own field list rather than going through fields_for_step.

    Its `default` is the single source of the value a skipped question stores —
    write_agent_row reads the same attribute rather than repeating the literal.
    Two copies of a default agree only until one of them is edited (TMDEV-74).
    """
    return Field(
        "AGENT_EFFORT", "Effort level", kind="select", choices=list(adapter.EFFORTS),
        default=adapter.DEFAULT_EFFORT, advanced=True,
        help="How hard this agent thinks on each run, when nothing overrides it. Individual "
             "videos can pick their own at the topic checkpoint, and this is editable "
             "afterwards on the Settings dashboard. Higher levels cost more per run and take "
             "longer; 'high' is the default because a pipeline run writes scripts and scene "
             "code that a human then has to review.")



def install_fields(adapter, suggestions: list, probe) -> list:
    """The questions for one agent's install, in order.

    The scope question is omitted for an agent with a single scope: asking a
    question that has one answer is noise, and run_install_agent seeds the
    value instead. Extracted from run_install_agent so it can be asserted
    without driving the whole flow.
    """
    fields = [run_path_field(adapter.name), WIPE_FIELD,
              models_field(adapter, suggestions, probe), effort_field(adapter)]
    if len(adapter.SUPPORTED_SCOPES) > 1:
        fields.insert(0, scope_field(adapter))
    return fields


def probe_effort(adapter, binary: str, effort: str, model: str = "") -> str | None:
    """Warn text when the installed CLI does not accept --effort, else None.

    One real (tiny) run, and the point of it is timing: an older CLI that has
    never heard of the flag exits non-zero having done NOTHING, so without this
    the first sign of trouble is a silently wasted 3am cron tick. poll.py falls
    back at runtime either way — this just moves the discovery to a moment when
    a human is watching.

    Anything other than a clean "does not know the flag" verdict returns None:
    a network blip or a timeout is not evidence about the flag, and blocking or
    warning on one would cry wolf on every flaky install.
    """
    if not adapter.EFFORT_UNSUPPORTED_MARKERS:
        # This agent cannot reject the effort at all — see its adapter. A probe
        # here would be a real, billed session that could never say anything.
        return None
    if not model and not adapter.PROBES_EFFORT_WITHOUT_A_MODEL:
        # This agent's rejection depends on the model/effort PAIR, so a
        # model-less probe proves nothing and would still be billed.
        return None
    with tempfile.TemporaryDirectory() as tmp:
        try:
            r = subprocess.run(adapter.probe_argv(binary, model, effort), cwd=tmp,
                               capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECS)
        except (OSError, subprocess.TimeoutExpired):
            return None
    if not adapter.effort_rejected(r.stderr or "", r.returncode, r.stdout or ""):
        return None
    if not adapter.PROBES_EFFORT_WITHOUT_A_MODEL:
        # A pair-level rejection: the level is fine, this model cannot use it.
        # Selected on the adapter, not on "was a model passed" — every adapter
        # is probed with one now, so that test would hand an older Claude CLI
        # that rejects the flag outright the wrong advice entirely.
        return (f"{adapter.display_name} does not accept effort '{effort}' with {model}. That "
                f"level will be ignored and every run uses the CLI's own default effort. Pick a "
                f"different level or default model, then re-run this command.")
    return (f"{adapter.display_name} does not accept --effort. The stored level "
            f"('{effort}') will be ignored and every run uses the CLI's own default "
            f"effort. Upgrade the CLI and re-run this command.")


def make_probe(adapter, binary: str):
    """A model check for the models field: KeyCheck VALID/INVALID/UNKNOWN.

    Rejection is read from the output, never the exit code — the Claude CLI
    exits 0 on a model it does not recognise. A non-zero exit *without* the
    marker is some other failure, so it is UNKNOWN (kept, with a warning)
    rather than a verdict on the model.
    """
    def probe(model: str) -> api_keys.KeyCheck:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                r = subprocess.run(adapter.probe_argv(binary, model), cwd=tmp,
                                   capture_output=True, text=True, timeout=PROBE_TIMEOUT_SECS)
            except (OSError, subprocess.TimeoutExpired) as e:
                return api_keys.KeyCheck(
                    api_keys.UNKNOWN, f"Could not check {model} ({type(e).__name__}) — kept "
                                      "unverified.")
        if adapter.model_rejected(f"{r.stdout}\n{r.stderr}", r.returncode):
            return api_keys.KeyCheck(
                api_keys.INVALID, f"{adapter.display_name} does not recognise '{model}', or this "
                                  "account cannot use it.")
        if r.returncode != 0:
            return api_keys.KeyCheck(
                api_keys.UNKNOWN, f"The check for {model} exited {r.returncode} without "
                                  "confirming it — kept unverified.")
        return api_keys.KeyCheck(api_keys.VALID, f"{model} verified.")
    return probe


def current_values(agent_id: str, db_path: Path = DB_PATH) -> dict:
    """Pre-fill for every question: the agent's own row on a re-run, the
    pre-agents settings rows on an upgrade's first run, defaults otherwise."""
    def usable(path) -> str:
        # A stored path that would now be refused (the old shared
        # ~/.tubematic-agent, which holds the logs) falls back to the default
        # rather than pre-filling an answer the question would reject.
        #
        # `include_config=False` deliberately: a foreign config document in the
        # agent's workspace is fixed by removing that file, never by moving the
        # agent. Falling back here would relocate it silently — and `upgrade.py`
        # takes these values without asking anything, so it would redeploy to a
        # directory the agents row does not record and leave the scheduled runs
        # on the old one. The question still rejects it and says what to remove.
        if path and not workspace_conflict(path, agent_id, db_path, include_config=False):
            return path
        return default_run_path(agent_id)

    def usable_scope(scope: str) -> str:
        # A stored scope this agent cannot honour — a legacy settings row, or a
        # hand-edited agents row — would otherwise reach deploy() and be acted
        # on as if it were supported.
        scopes = ADAPTERS[agent_id].SUPPORTED_SCOPES
        return scope if scope in scopes else scopes[0]

    row = next((a for a in read_agents(db_path) if a["id"] == agent_id), None)
    if row:
        return {
            "INSTALL_SCOPE": usable_scope(row.get("install_scope") or "user"),
            "AGENT_RUN_PATH": usable(row.get("run_path")),
            "WIPE_AGENT_WORKSPACE": "false",
            "AGENT_MODELS": json.dumps(row["models"]),
            "AGENT_EFFORT": row.get("effort") or ADAPTERS[agent_id].DEFAULT_EFFORT,
        }
    settings = read_settings(db_path)
    return {
        "INSTALL_SCOPE": usable_scope(settings.get("install_scope") or "user"),
        "AGENT_RUN_PATH": usable(settings.get("agent_run_path")),
        "WIPE_AGENT_WORKSPACE": "false",
        "AGENT_MODELS": "[]",
        "AGENT_EFFORT": ADAPTERS[agent_id].DEFAULT_EFFORT,
    }


def config_root_conflict(adapter) -> tuple | None:
    """(message, hint) when this agent's config root is not the default, else None.

    The root holds the agent's authentication AND the skills this installer
    deploys, and it can be chosen by an environment variable that cron strips
    (HOME/LOGNAME/PATH/SHELL is all a cron job gets). So an install made under
    a non-default root verifies and then runs every scheduled tick against a
    different one: no skills, and almost certainly logged out.

    Checked at EVERY lifecycle entry point, not just install. The dangerous
    case is not only installing under an override — it is setting one *after*
    a normal install, which would make an upgrade deploy into a root the
    scheduled runs never read, and an uninstall archive the agent while leaving
    its real skills and MCP registration in place.
    """
    configured = getattr(adapter, "config_home", None)
    if configured is None:
        return None
    # The root cron will use, asked for directly, rather than a hardcoded
    # ~/.<name>: agents do not agree on where their config lives (Codex uses
    # ~/.codex, OpenCode ~/.config/opencode), so a guessed default reported a
    # perfectly ordinary install as overridden. Asking the adapter for the
    # same root twice — once honouring the environment, once not — is what the
    # question actually is.
    default = configured(respect_override=False)
    if configured() == default:
        return None
    return (f"{adapter.display_name} is using {configured()} as its config root, not {default}",
            f"cron does not pass that environment on, so scheduled runs would use {default} — "
            f"without the skills installed here, and probably logged out. Re-run with the "
            f"environment variable unset, after logging the CLI in against the default root")


def check_preconditions(adapter, *, verify: bool, dry_run: bool, rep) -> str | None:
    """The binary to install, or None when a blocker was reported.

    Under --dry-run every blocker is downgraded to a warning, the same as the
    main wizard's prerequisites: the point of a dry run is previewing the
    questions on a machine that is not ready yet.
    """
    blocked = False

    def _block(msg: str, hint: str) -> None:
        nonlocal blocked
        rep.warn(f"{msg} — {hint}")
        if not dry_run:
            blocked = True

    if not DB_PATH.exists():
        _block("No Tubematic database yet", "run `python onboard.py` first — the project is set "
                                            "up before its agents")
    binary = shutil.which(adapter.binary_name)
    if not binary:
        _block(f"'{adapter.binary_name}' is not in PATH", f"install {adapter.display_name} first")
    elif verify:
        try:
            r = subprocess.run(adapter.auth_status_argv(binary), capture_output=True, text=True,
                               timeout=AUTH_TIMEOUT_SECS)
        except (OSError, subprocess.TimeoutExpired) as e:
            rep.warn(f"Could not check the {adapter.display_name} login ({type(e).__name__}) — "
                     "continuing. Cron runs unattended, so make sure it is logged in.")
        else:
            if adapter.logged_in(r.stdout, r.stderr, r.returncode):
                rep.ok(f"{adapter.display_name} is logged in")
            else:
                _block(f"{adapter.display_name} is not logged in",
                       f"{adapter.LOGIN_HINT}, then re-run this")
    conflict = config_root_conflict(adapter)
    if conflict:
        _block(*conflict)

    if blocked:
        return None
    return binary or adapter.binary_name


def resolve_workspace(adapter, values: dict) -> Path:
    """The workspace this install will use. One definition, because `deploy`
    and the preflight below must not be able to disagree about it."""
    return Path(values.get("AGENT_RUN_PATH") or default_run_path(adapter.name)) \
        .expanduser().resolve()


def deploy(adapter, binary: str, values: dict, *, ex: Executor, rep) -> Path:
    """Skills, commands, MCP registration, allowlist, trust, logs directory.
    Returns the resolved workspace. Idempotent: `Executor.copytree` replaces
    each shipped skill directory wholesale and RETIRED_SKILLS are removed, so a
    re-run is a clean redeploy that leaves every other skill alone."""
    mcp_port = read_settings(DB_PATH).get("mcp_port") or "4100"
    mcp_url = f"http://localhost:{mcp_port}/mcp"
    scope = values.get("INSTALL_SCOPE", "user")
    workspace = resolve_workspace(adapter, values)
    agent = adapter.name
    skills_src = REPO_ROOT / "agent_files" / "skills"
    commands_src = REPO_ROOT / "agent_files" / agent / "commands"

    if workspace.exists() and values.get("WIPE_AGENT_WORKSPACE") == "true":
        ex.rmtree(workspace)
        rep.ok(f"Workspace deleted: {workspace}")
    elif workspace.exists():
        rep.info("Keeping the existing workspace — files are overwritten in place.")

    if scope == "project":
        ex.mkdir(workspace)
        rep.ok(f"Workspace: {workspace}")
        skills_dest = adapter.project_skills_dir(workspace)
        commands_dest = adapter.project_commands_dir(workspace)
        mcp_cwd, mcp_label = workspace, "local scope in agent workspace"
        remotion_cwd, remotion_global = workspace, False
    else:
        home = Path.home()
        skills_dest = adapter.user_skills_dir(home)
        commands_dest = adapter.user_commands_dir(home)
        mcp_cwd, mcp_label = REPO_ROOT, "user scope — available in all projects"
        remotion_cwd, remotion_global = home, True

    _copy_skills(skills_src, skills_dest, f"{skills_dest}/", ex=ex, rep=rep)
    _sweep_retired_skills(skills_dest, ex=ex, rep=rep)
    if adapter.HAS_COMMANDS and commands_dest is not None:
        _copy_commands(commands_src, commands_dest, f"{commands_dest}/", agent, ex=ex, rep=rep)
    auth = mcp_auth()
    if not adapter.MCP_ADD_REPLACES:
        # This CLI refuses to add a name that exists, so drop any previous
        # registration first. Its failure on a first install is expected.
        ex.run(adapter.mcp_remove_argv(binary, scope), cwd=mcp_cwd)
    _register_mcp(adapter.mcp_add_argv(binary, scope, mcp_url, auth), mcp_cwd, mcp_label, mcp_url,
                  ex=ex, rep=rep)
    if hasattr(adapter, "set_mcp_header_helper"):
        _patch_mcp_header_helper(adapter, auth, ex=ex, rep=rep)
    _install_remotion_skills(remotion_cwd, adapter.REMOTION_AGENT_FLAG,
                             global_scope=remotion_global, ex=ex, rep=rep)

    if scope != "project":
        ex.mkdir(workspace)
        rep.ok(f"Agent workspace: {workspace}")
        if adapter.COPIES_SKILLS_INTO_WORKSPACE:
            # cron runs the agent from here, and this agent only finds its
            # skills relative to its own working directory.
            dest = adapter.project_skills_dir(workspace)
            _copy_skills(skills_src, dest, f"{dest}/", ex=ex, rep=rep)
            _sweep_retired_skills(dest, ex=ex, rep=rep)

    if adapter.NEEDS_ALLOWLIST:
        _write_agent_allowlist(workspace, ex=ex, rep=rep)
    if adapter.NEEDS_PERMISSION_CONFIG:
        _write_agent_permissions(adapter, workspace, mcp_url, auth, ex=ex, rep=rep)
    reload_argv = getattr(adapter, "reload_argv", None)
    if reload_argv:
        # OpenCode answers from a background service that caches its config. Seen
        # live after an upgrade: the service kept its old, token-less connection
        # (401s) until something reloaded it, so a redeploy reloads it itself.
        r = ex.run(reload_argv(binary))
        if r.returncode == 0:
            rep.ok(f"{adapter.display_name} reloaded its config")
        else:
            rep.warn(f"{adapter.display_name} did not reload its config — run: "
                     f"{' '.join(reload_argv(binary))}")
    # Shared by every agent and outside every workspace; the cron step makes
    # it too, but an agent install must not depend on that having run.
    ex.mkdir(POLL_LOG_DIR)
    rep.ok(f"Poll logs directory: {POLL_LOG_DIR}")
    return workspace


def write_agent_row(adapter, binary: str, values: dict, workspace: Path, models: list, *,
                    verified: bool, ex: Executor) -> None:
    """Insert or update the agent's row, then drop the settings rows it replaces.

    A re-install keeps the row's weight and default flag, and un-archives it.
    The first live agent becomes the default. `verified_at` stays blank when
    the models were not actually probed (--disable-verification), so the
    dashboard can say so rather than implying a check that never ran.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    verified_at = now if verified else ""
    # The effort field's own `default`, not a second literal of it: a skipped
    # (advanced) question is identical to answering it with its default only
    # while both copies agree, and one of two copies always gets edited alone.
    effort = values.get("AGENT_EFFORT") or effort_field(adapter).default
    fields = (adapter.display_name, binary, str(workspace), values.get("INSTALL_SCOPE", "user"),
              json.dumps(models), effort, verified_at)
    # Read outside the write: Executor.sqlite_write's callback is for writes
    # only, and is not called at all under --dry-run.
    agents = read_agents(DB_PATH)
    exists = any(a["id"] == adapter.name for a in agents)
    make_default = not any(a.get("is_default") and not a.get("archived_at")
                           and a["id"] != adapter.name for a in agents)

    def _write(con):
        con.execute(AGENTS_SCHEMA)
        if exists:
            con.execute(
                "UPDATE agents SET name = ?, binary = ?, run_path = ?, install_scope = ?, "
                "models = ?, effort = ?, verified_at = ?, archived_at = NULL, updated_at = ? "
                "WHERE id = ?",
                (*fields, now, adapter.name))
            if make_default:
                con.execute("UPDATE agents SET is_default = 1 WHERE id = ?", (adapter.name,))
        else:
            con.execute(
                "INSERT INTO agents (id, name, binary, run_path, install_scope, models, "
                "effort, verified_at, is_default, weight, archived_at, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, NULL, ?, ?)",
                (adapter.name, *fields, 1 if make_default else 0, now, now))
        con.execute(
            f"DELETE FROM settings WHERE key IN ({','.join('?' * len(LEGACY_SETTING_ROWS))})",
            LEGACY_SETTING_ROWS)

    ex.sqlite_write(DB_PATH, _write, f"record agent '{adapter.name}'")


def run_install_agent(name: str, *, dry_run: bool = False, allow_skipping: bool = False,
                      verify_keys: bool = True, full_questionnaire: bool = False) -> int:
    """The whole --install-agent flow. Returns a process exit code.

    `full_questionnaire` is --full-questionnaire, and this flow has to honour
    it by hand: it builds its own field list rather than going through
    config.fields_for_step, which is where the main wizard's `advanced` filter
    lives. Without the filter here an `advanced` field would simply always be
    asked, which is the opposite of what the attribute means.
    """
    # Deferred, as in run_wizard: prompt.py imports from plain.py.
    from rich.rule import Rule
    from onboard.plain import PlainReporter, console, print_verify
    from onboard.prompt import PromptOptions, _PreviewReporter, prompt_fields

    adapter = ADAPTERS[name]
    # A model probe is a real (tiny) agent run, so a dry run never probes, and
    # neither does --disable-verification.
    verify = verify_keys and not dry_run
    rep = PlainReporter(dry_run=dry_run)

    console.print()
    console.print(Rule(f"[bold] Install agent: {adapter.display_name} ({name}) [/bold]",
                       style="blue"))
    if not verify_keys:
        console.print("  [yellow]![/yellow]  [dim]--disable-verification: the login and the "
                      "models are not checked.[/dim]")

    binary = check_preconditions(adapter, verify=verify, dry_run=dry_run, rep=rep)
    if binary is None:
        console.print("\n[red]Fix the above and re-run.[/red]\n")
        return 1

    cfg = OnboardConfig(values=current_values(name))
    if len(adapter.SUPPORTED_SCOPES) == 1:
        # install_fields omits the question; the value still has to be stored.
        cfg.values["INSTALL_SCOPE"] = adapter.SUPPORTED_SCOPES[0]
    suggestions = adapter.suggest_models(shutil.which(binary) or binary)
    fields = install_fields(adapter, suggestions, make_probe(adapter, binary))
    if not full_questionnaire:
        fields = [f for f in fields if not f.advanced]

    def _before(field) -> None:
        # The wipe decision needs to see what is there, not just a yes/no.
        # Same predicate as the question's own condition, so the preview never
        # appears without the question or vice versa.
        if field is WIPE_FIELD and agent_workspace_exists(cfg.values):
            describe_existing_workspace(Path(cfg.values["AGENT_RUN_PATH"]).expanduser(),
                                        _PreviewReporter(), adapter)

    opts = PromptOptions(allow_skipping=allow_skipping, verify_keys=verify)
    try:
        prompt_fields(fields, cfg, opts=opts, before_field=_before)
    except SystemExit:
        console.print("\n[dim]Agent install cancelled.[/dim]\n")
        return 1

    try:
        models = json.loads(cfg.values.get("AGENT_MODELS") or "[]")
    except json.JSONDecodeError:
        models = []

    # Probed whether or not the question was asked, because the default install
    # is the one that never asks and is also the common one — and the failure
    # this catches (an older CLI that has never heard of --effort) otherwise
    # first shows up as a silently wasted cron tick. Never a blocker: poll.py
    # drops the flag at runtime, so a warned install still works.
    effort = cfg.values.get("AGENT_EFFORT") or effort_field(adapter).default
    if verify:
        # The default model, because for some agents the rejection depends on
        # the model/effort pair rather than on the level alone.
        warning = probe_effort(adapter, binary, effort, models[0] if models else "")
        if warning:
            rep.warn(warning)

    ex = Executor(dry_run=dry_run, reporter=rep)
    try:
        if DB_PATH.exists() and not _ensure_db_writable(ex, rep):
            return 1
        workspace = deploy(adapter, binary, cfg.values, ex=ex, rep=rep)
        write_agent_row(adapter, binary, cfg.values, workspace, models, verified=verify, ex=ex)
    except Exception as e:
        console.print(f"[red]Agent install failed: {e}[/red]")
        return 1

    default = models[0] if models else "the CLI's own default"
    rep.ok(f"{adapter.display_name} installed as agent '{name}' — default model: {default}, "
           f"effort: {effort}")
    rep.info("Pick the default agent, each agent's share of new videos, and each agent's default "
             "model and effort level on the dashboard's Settings → Agents tab.")
    print_verify()
    return 0


# ── --uninstall-agent ───────────────────────────────────────────────────────

def deployed_paths(adapter, row: dict) -> list:
    """The skill directories and command files `deploy` put down for this
    agent's scope, and that still exist. Named from this checkout's
    agent_files plus RETIRED_SKILLS (an install never upgraded since still
    holds them), so anything else in that agent's own directories is never
    touched."""
    skills = [d.name for d in (REPO_ROOT / "agent_files" / "skills").iterdir() if d.is_dir()] \
        if (REPO_ROOT / "agent_files" / "skills").is_dir() else []
    skills += [n for n in RETIRED_SKILLS if n not in skills]
    commands_src = REPO_ROOT / "agent_files" / adapter.name / "commands"
    commands = [f.name for f in commands_src.glob("*.md")] \
        if adapter.HAS_COMMANDS and commands_src.is_dir() else []
    workspace = Path(row.get("run_path") or default_run_path(adapter.name)).expanduser()
    if (row.get("install_scope") or "user") == "project":
        roots = [(adapter.project_skills_dir(workspace), adapter.project_commands_dir(workspace))]
    else:
        home = Path.home()
        roots = [(adapter.user_skills_dir(home), adapter.user_commands_dir(home))]
        if adapter.COPIES_SKILLS_INTO_WORKSPACE:
            # deploy copies the skills into the workspace too, for cron's cwd.
            roots.append((adapter.project_skills_dir(workspace), None))
    out = []
    # Tubematic's own config document. The workspace is Tubematic's directory,
    # so this goes with the skills rather than being edited.
    managed = getattr(adapter, "managed_config_files", None)
    if managed is not None:
        out += [f for f in managed(workspace) if f.is_file()]
    for skills_dir, commands_dir in roots:
        if skills_dir is not None:
            out += [skills_dir / s for s in skills if (skills_dir / s).is_dir()]
        if commands_dir is not None:
            out += [commands_dir / c for c in commands if (commands_dir / c).is_file()]
    return out


def uninstall(adapter, row: dict, *, ex: Executor, rep) -> None:
    """Remove what the installer deployed, then mark the row uninstalled.

    The workspace itself stays (user decision — it may hold the agent's own
    working files), and so do its allowlist and trust record, which only
    matter to a workspace an agent runs in. The poll logs are outside every
    workspace, so they are never at stake here. The row is archived, never deleted, so a video pinned to
    this agent keeps resolving it (the poller logs and skips it), and
    --install-agent brings the same row back.
    """
    for path in deployed_paths(adapter, row):
        (ex.rmtree if path.is_dir() else ex.unlink)(path)
    rep.ok("Skills and commands removed")

    scope = row.get("install_scope") or "user"
    workspace = Path(row.get("run_path") or default_run_path(adapter.name)).expanduser()
    binary = shutil.which(row.get("binary") or "") or shutil.which(adapter.binary_name)
    remove_argv = adapter.mcp_remove_argv(adapter.binary_name, scope)
    if remove_argv is None:
        # This agent has no deregistration command at all, so the entry its
        # `mcp add` wrote is removed from the config document instead. Doing it
        # here rather than inventing an argv is what keeps an uninstall from
        # reporting success for a command that was never run.
        _remove_mcp_entry(adapter, workspace, scope, ex=ex, rep=rep)
        _archive_agent_row(adapter, ex=ex)
        return
    argv_hint = " ".join(remove_argv)
    if not binary:
        rep.warn(f"'{adapter.binary_name}' not found — MCP server not deregistered. "
                 f"Run manually: {argv_hint}")
    else:
        cwd = workspace if scope == "project" and workspace.is_dir() else REPO_ROOT
        r = ex.run(adapter.mcp_remove_argv(binary, scope), cwd=cwd)
        if r.returncode == 0:
            rep.ok(f"MCP server deregistered ({scope} scope)")
        else:
            rep.warn(f"MCP remove failed: {(r.stderr or '').strip()} — run manually: {argv_hint}")

    _archive_agent_row(adapter, ex=ex)


def _remove_mcp_entry(adapter, workspace: Path, scope: str, *, ex: Executor, rep) -> None:
    """Drop `mcp.servers.tubematic` from the document this scope registered it in.

    Only that one key: the document is the operator's own agent configuration
    at user scope, and everything else in it belongs to them. The edit is made
    on the TEXT rather than by reserialising, so comments survive — and it is
    verified before it is written, so a shape the editor mis-reads reports the
    change instead of performing it.
    """
    path = adapter.mcp_config_file(Path.home(), workspace, scope)
    if not path.exists():
        rep.info(f"No {path} — nothing to deregister")
        return
    original = path.read_text()
    edited = adapter.remove_mcp_entry(original)
    if edited is None:
        try:
            registered = "tubematic" in (adapter.parse_config(original)
                                         .get("mcp", {}).get("servers", {}))
        except Exception:
            registered = True
        if not registered:
            rep.info(f"No tubematic MCP entry in {path} — nothing to deregister")
            return
        rep.warn(f"Could not safely edit {path} — remove the \"tubematic\" entry under "
                 f"mcp.servers by hand")
        return
    ex.write_file(path, edited)
    rep.ok(f"MCP server deregistered ({scope} scope) — {path}")


def _archive_agent_row(adapter, *, ex: Executor) -> None:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ex.sqlite_write(DB_PATH, lambda con: con.execute(
        "UPDATE agents SET archived_at = ?, is_default = 0, updated_at = ? WHERE id = ?",
        (now, now, adapter.name)), f"mark agent '{adapter.name}' uninstalled")


def run_uninstall_agent(name: str, *, dry_run: bool = False, confirm=None) -> int:
    """The whole --uninstall-agent flow. Returns a process exit code.
    `confirm` is injectable for tests; it defaults to a y/N prompt."""
    from rich.prompt import Confirm
    from rich.rule import Rule
    from onboard.plain import PlainReporter, console

    confirm = confirm or (lambda msg: Confirm.ask(msg, default=False))
    adapter = ADAPTERS[name]
    rep = PlainReporter(dry_run=dry_run)
    console.print()
    console.print(Rule(f"[bold] Uninstall agent: {adapter.display_name} ({name}) [/bold]",
                       style="blue"))

    conflict = config_root_conflict(adapter)
    if conflict:
        # Surfaced on BOTH paths. A live run is refused, because it would
        # archive the row while removing nothing, leaving the real skills and
        # MCP registration behind and the agent looking uninstalled. A dry run
        # continues — previewing is its job — but must say so, or it previews
        # a root the real run would never touch.
        rep.warn(f"{conflict[0]} — {conflict[1]}")
        if not dry_run:
            console.print("\n[red]Fix the above and re-run.[/red]\n")
            return 1

    agents = read_agents(DB_PATH)
    row = next((a for a in agents if a["id"] == name), None)
    if row is None:
        rep.warn(f"'{name}' is not installed — nothing to do.")
        return 1
    if row.get("archived_at"):
        rep.info(f"'{name}' is already uninstalled. Re-install it with "
                 f"`python onboard.py --install-agent {name}`.")
        return 0
    others = [a for a in agents if a["id"] != name and not a.get("archived_at")]
    # Uninstalling the default while another agent is live would leave dispatch
    # to the "oldest live" fallback — a default nobody chose. The last agent may
    # go: nothing is left to choose between.
    if row.get("is_default") and others:
        rep.warn(f"'{name}' is the default agent — make another agent the default on the "
                 "dashboard's Settings → Agents tab first.")
        return 1

    paths = deployed_paths(adapter, row)
    rep.info(f"Removes {len(paths)} deployed skill/command path(s) and the tubematic MCP "
             f"registration ({row.get('install_scope') or 'user'} scope), and marks the agent "
             "uninstalled.")
    rep.info(f"Keeps the workspace {row.get('run_path')}, the shared poll logs, and every video "
             "already assigned to this agent, which is skipped until it is re-installed.")
    if not dry_run and not confirm(f"Uninstall {adapter.display_name}?"):
        console.print("\n[dim]Agent uninstall cancelled.[/dim]\n")
        return 1

    ex = Executor(dry_run=dry_run, reporter=rep)
    try:
        if not _ensure_db_writable(ex, rep):
            return 1
        uninstall(adapter, row, ex=ex, rep=rep)
    except Exception as e:
        console.print(f"[red]Agent uninstall failed: {e}[/red]")
        return 1
    rep.ok(f"{adapter.display_name} uninstalled. Re-install with "
           f"`python onboard.py --install-agent {name}`.")
    if not others:
        rep.warn("No agent is installed now — nothing runs until one is.")
    return 0


# ── --list-agents ───────────────────────────────────────────────────────────

def print_agents() -> None:
    """Supported and installed agents. Plain and non-interactive, like --status."""
    from onboard.plain import console

    console.print()
    console.print("[bold]Supported agents[/bold]")
    for key in sorted(ADAPTERS):
        console.print(f"  {key:<10} {ADAPTERS[key].display_name}")
    console.print()
    console.print("[bold]Installed agents[/bold]")
    agents = read_agents(DB_PATH)
    if not agents:
        console.print("  none — install one with: python onboard.py --install-agent <agent>")
    for a in agents:
        if a.get("archived_at"):
            state = "[dim]uninstalled[/dim]"
        else:
            state = "[green]installed[/green]" + (", [bold]default agent[/bold]"
                                                 if a.get("is_default") else "")
        models = ", ".join(f"{m} (default)" if i == 0 else m for i, m in enumerate(a["models"]))
        console.print(f"  {a['id']:<10} {a.get('name', '')} — {state}")
        console.print(f"             weight {a.get('weight')}   models: {models or '—'}")
        console.print(f"             workspace {a.get('run_path')} ({a.get('install_scope')} "
                      f"scope)   verified {a.get('verified_at') or 'never'}")
    console.print()
