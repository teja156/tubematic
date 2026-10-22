"""Prerequisite and installation checks — structured results, no printing.

Callers (onboard/plain.py's print_prereq/print_verify/--status) render
these however fits their surface.
"""
import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from onboard.config import (DATA_ROOT, DATA_SUBDIRS, POLL_LOG_DIR, REPO_ROOT, DB_PATH,
                            read_agents, read_settings)


@dataclass
class CheckItem:
    label: str
    ok: bool
    severity: str = "error"   # "error" blocks; "warning"/"info" never does
    hint: str = ""


def _run(cmd: list) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=REPO_ROOT, text=True, capture_output=True)


# ── Prerequisites ───────────────────────────────────────────────────────────

def check_prerequisites(mode: str = "dev") -> list:
    """Hard requirements (Docker, compose, Python) plus warn-only checks
    (Node/npx) plus the read-only tubematic.db ownership check. The agent
    binary and its login are --install-agent's preconditions, not these.

    The ownership check surfaces a root-owned tubematic.db* (left by a
    prior install's containers) as a read-only os.stat here, before any
    prompting starts — so the fix (a plain `sudo chown` the user runs
    themselves) is visible up front instead of appearing as a surprise
    mid-wizard failure once `pipeline_settings` actually tries to write.
    A data subdirectory this user cannot write gets the same treatment.

    Node/npx are warn-only but are checked in every install mode. `mode` no
    longer changes any check; it stays in the signature because all three
    entry points resolve an install mode and pass the one they ran for.
    """
    import sys

    items = []

    items.append(CheckItem(
        f"Python 3.11+ (found {sys.version.split()[0]})",
        sys.version_info >= (3, 11),
    ))

    docker_found = bool(shutil.which("docker"))
    if not docker_found:
        items.append(CheckItem("Docker installed", False, hint="install Docker Desktop or Docker Engine"))
    else:
        running = _run(["docker", "info"]).returncode == 0
        items.append(CheckItem("Docker running", running,
                                hint="Docker installed but not running — start Docker and re-run" if not running else ""))
        compose_ok = _run(["docker", "compose", "version"]).returncode == 0
        items.append(CheckItem("docker compose v2", compose_ok,
                                hint="update Docker Desktop or install the Compose plugin" if not compose_ok else ""))

    # Checked in every install mode. The only host-side consumer of Node is
    # _install_remotion_skills, which --install-agent runs whatever the mode
    # is, so the old release-mode skip (TMDEV-91 Phase 2, reasoning that a
    # release install builds nothing locally) hid a prerequisite a release
    # install needs just as much: the local build is not what wants Node.
    node_bin = shutil.which("node")
    if node_bin:
        version_str = _run(["node", "--version"]).stdout.strip()
        try:
            major, minor = (int(x) for x in version_str.lstrip("v").split(".")[:2])
        except ValueError:
            major, minor = 0, 0
        node_ok = (major, minor) >= (22, 20)
        items.append(CheckItem(
            f"Node.js {version_str}", node_ok, severity="warning",
            hint="" if node_ok else
                 f"Node.js {version_str} found, but the remotion-dev/skills installer requires "
                 ">= 22.20.0 — it will crash on import (not just warn), so remotion-best-practices "
                 "will silently fail to install. Upgrade Node.js.",
        ))
    else:
        items.append(CheckItem(
            "Node.js", False, severity="warning",
            hint="not found — --install-agent cannot install the remotion-best-practices "
                 "skill, which the scene-writing skill invokes first. Container rendering is "
                 "unaffected. Node.js >= 22.20 is needed for a release install too."))

    items.append(CheckItem(
        "npx available", bool(shutil.which("npx")), severity="warning",
        hint="" if shutil.which("npx") else
             "comes with Node.js; without it remotion-dev/skills is skipped on every "
             "--install-agent."))

    # Read-only ownership probe — a prior install's containers (root-owned)
    # may have left tubematic.db*/-wal/-shm owned by root.
    db_dir = DB_PATH.parent
    if db_dir.exists():
        target = f"{os.getuid()}:{os.getgid()}"
        for f in sorted(db_dir.glob("tubematic.db*")):
            try:
                owned = f.stat().st_uid == os.getuid()
            except OSError:
                continue
            items.append(CheckItem(
                f"{f.name} owned by current user", owned, severity="warning",
                hint=f"Run: sudo chown {target} {f}" if not owned else "",
            ))

    # Read-only write probe on each data subdirectory. The containers run as
    # root and do not care, but host-side writers do: poll.py appends its
    # poll.<date>.jsonl to logs/ from cron as this user, and a root-owned
    # logs/ used to drop every poll entry from the dashboard silently
    # (TMDEV-94). Only an existing directory is judged -- the directories step
    # creates a missing one as this user, which is the right owner. W_OK alone
    # is not enough: creating a file in a directory also needs search (X_OK).
    target = f"{os.getuid()}:{os.getgid()}"
    for d in DATA_SUBDIRS:
        path = DATA_ROOT / d
        if path.is_dir() and not os.access(path, os.W_OK | os.X_OK):
            items.append(CheckItem(
                f"{path} writable by current user", False, severity="warning",
                hint=f"Run: sudo chown {target} {path}",
            ))

    return items


# ── Installation check ───────────────────────────────────────────────────────

def _has_allowlist(settings_path: Path) -> bool:
    try:
        data = json.loads(settings_path.read_text())
        return "mcp__tubematic" in data.get("permissions", {}).get("allow", [])
    except Exception:
        return False


def _has_data_dir_deny(settings_path: Path) -> bool:
    """Whether the workspace allowlist denies Read on the data directory."""
    from onboard.actions import claude_read_denies
    try:
        data = json.loads(settings_path.read_text())
        deny = data.get("permissions", {}).get("deny", [])
        return all(rule in deny for rule in claude_read_denies())
    except Exception:
        return False


def _has_trust(workspace: Path) -> bool:
    claude_json = Path.home() / ".claude.json"
    if not claude_json.exists():
        return False
    try:
        data = json.loads(claude_json.read_text())
        return bool(data.get("projects", {}).get(str(workspace), {}).get("hasTrustDialogAccepted"))
    except Exception:
        return False


def _read_agent_config_quietly(adapter, path: Path) -> dict | None:
    """The agent's config document, or None. Parsed through the adapter, since
    an agent's config may be JSONC — OpenCode accepts comments and trailing
    commas in a plain `.json`, and `json.loads` would report a valid config as
    a failed install."""
    try:
        data = adapter.parse_config(path.read_text())
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _mcp_options_applied(adapter, path: Path) -> bool:
    """Whether the registered server carries the options the install sets.

    Separate from "registered" because the two now fail apart: the installer
    refuses to rewrite a config document that carries comments — rewriting it
    would delete them — and reports the edit for the operator to make by hand.
    Without this check `--status` would call that install healthy while the
    agent cannot see a single one of its tools.
    """
    patch = getattr(adapter, "MCP_SERVER_OPTIONS", None)
    if not patch:
        return True
    data = _read_agent_config_quietly(adapter, path)
    server = ((data or {}).get("mcp") or {}).get("servers", {}).get("tubematic")
    return isinstance(server, dict) and all(server.get(k) == v for k, v in patch.items())


def _mcp_registered_in_config(adapter, path: Path) -> bool:
    """Whether a config document names the tubematic MCP server.

    Used in preference to shelling out for any agent whose adapter can name the
    document. It is not merely cheaper — it is the only reliable answer for an
    agent that answers from a background service: OpenCode's `mcp list` reports
    "No MCP servers configured" for several seconds after any config change or
    service restart, and a checklist that believed it would tell the user to
    re-run an install that had in fact just succeeded.
    """
    data = _read_agent_config_quietly(adapter, path)
    servers = ((data or {}).get("mcp") or {}).get("servers")
    return isinstance(servers, dict) and "tubematic" in servers


def _has_permission_rules(adapter, workspace: Path) -> bool:
    """Whether the managed rules are the LAST rules in the workspace config.

    Membership is not enough, and the gap is exploitable: the permissions are
    resolved last-match-wins, so a managed rule followed by a later
    contradicting one leaves the later one in force while a membership test
    still reports the install as correct. Verified — a `read *.env deny`
    followed by a `read *.env allow` read the file. The check therefore asserts
    the same thing the installer writes: the managed rules, in order, at the
    end.
    """
    from onboard.actions import managed_permission_rules

    data = _read_agent_config_quietly(adapter, adapter.managed_config_file(workspace))
    rules = (data or {}).get("permissions")
    if not isinstance(rules, list):
        return False
    wanted = managed_permission_rules(adapter)
    return rules[-len(wanted):] == wanted


def _mcp_registered_user(binary: str = "") -> bool:
    claude_bin = shutil.which(binary or "claude")
    if not claude_bin:
        return False
    try:
        r = subprocess.run([claude_bin, "mcp", "list"], capture_output=True, text=True, timeout=5)
        return "tubematic" in r.stdout
    except Exception:
        return False


def _mcp_registered_project(workspace: Path) -> bool:
    claude_json = Path.home() / ".claude.json"
    if not claude_json.exists():
        return False
    try:
        data = json.loads(claude_json.read_text())
        servers = data.get("projects", {}).get(str(workspace), {}).get("mcpServers", {})
        return "tubematic" in servers
    except Exception:
        return False


def _mcp_options_check(aid: str, adapter, workspace: Path, hint: str) -> "CheckItem":
    """The tool options are asserted in Tubematic's OWN document, not in the one
    `mcp add` wrote, so this reads the managed file.

    Separate from "registered" because the two answer different questions:
    whether an interactive session outside the workspace can reach the server,
    and whether a scheduled run inside it sees the tools natively rather than
    behind Code Mode.
    """
    config = adapter.managed_config_file(workspace)
    return CheckItem(f"[{aid}] MCP tool options applied ({config})",
                     _mcp_options_applied(adapter, config), hint=hint)


# A skill every install deploys, so its presence proves the copy really ran.
# Checking only that the skills *directory* exists is a false pass: the Remotion
# installer creates one too, so an agent whose own skills never landed still
# reported installed.
_PROOF_SKILL = "tubematic-operator"


# ── Authentication (TMDEV-152) ──────────────────────────────────────────────

def auth_items(db_path: Path = None) -> list:
    """The password and the three token files, read from disk."""
    import stat
    from tubematic_core import auth

    db_path = db_path or DB_PATH
    sdir = auth.secrets_dir()
    missing = []
    for name in auth.SECRET_NAMES:
        try:
            auth.read_secret(name, sdir)
        except auth.SecretMissing:
            missing.append(name)
    try:
        private = stat.S_IMODE(sdir.stat().st_mode) == 0o700
    except OSError:
        private = False
    return [
        CheckItem("Dashboard password set", auth.has_admin_password(db_path),
                  hint="python onboard.py --set-password"),
        CheckItem(f"Service tokens ({sdir})", not missing,
                  hint=f"missing {', '.join(missing)} — run: python onboard.py --step auth"),
        CheckItem("Service tokens directory is private (0700)", private, severity="warning",
                  hint=f"chmod 700 {sdir}"),
    ]


def mcp_auth_probe(url: str = "http://localhost:4100/mcp") -> tuple:
    """(refused without the token, accepted with it), probed live.

    Each is None when the server cannot be reached, so a stopped stack reads as
    "unknown" rather than as an open server.
    """
    import urllib.error
    import urllib.request
    from tubematic_core import auth

    body = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-06-18", "capabilities": {},
        "clientInfo": {"name": "tubematic-check", "version": "0"}}}).encode()

    def status(headers):
        req = urllib.request.Request(url, data=body, method="POST", headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream", **headers})
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                return r.status
        except urllib.error.HTTPError as e:
            return e.code
        except (urllib.error.URLError, OSError):
            return None

    without = status({})
    try:
        token = auth.read_secret("mcp_token")
    except auth.SecretMissing:
        return (None if without is None else without == 401), False
    with_token = status({"Authorization": f"Bearer {token}"})
    return (None if without is None else without == 401,
            None if with_token is None else with_token == 200)


def _helper_prints_a_header(helper: str) -> bool:
    import shlex
    try:
        r = subprocess.run(shlex.split(helper), capture_output=True, text=True, timeout=10)
        value = json.loads(r.stdout).get("Authorization", "") if r.returncode == 0 else ""
    except (OSError, ValueError, subprocess.TimeoutExpired, AttributeError):
        return False
    return value.startswith("Bearer ") and len(value) > len("Bearer ")


def _mcp_auth_wired(adapter, agent: dict, workspace: Path) -> bool:
    """Whether this agent's registration carries THIS install's auth.

    Compared with what --install-agent would write now, so an install that was
    moved (the helper path names the install directory) is reported too.
    """
    import tomllib
    from onboard.agent_install import mcp_auth

    auth = mcp_auth()
    scope = agent.get("install_scope") or "user"
    if hasattr(adapter, "set_mcp_header_helper"):
        try:
            data = tomllib.loads(adapter.config_toml(Path.home(), respect_override=False).read_text())
        except (OSError, tomllib.TOMLDecodeError):
            return False
        entry = data.get("mcp_servers", {}).get("tubematic", {})
        return entry.get("http_headers_helper") == auth.helper
    if hasattr(adapter, "auth_headers"):
        wanted = adapter.auth_headers(auth)
        documents = [adapter.mcp_config_file(Path.home(), workspace, scope, False)]
        if adapter.NEEDS_PERMISSION_CONFIG:
            documents.append(adapter.managed_config_file(workspace))
        for path in documents:
            data = _read_agent_config_quietly(adapter, path)
            entry = ((data or {}).get("mcp") or {}).get("servers", {}).get("tubematic")
            if not isinstance(entry, dict) or entry.get("headers") != wanted:
                return False
        return True
    try:
        data = json.loads((Path.home() / ".claude.json").read_text())
    except (OSError, ValueError):
        return False
    servers = data.get("mcpServers", {}) if scope == "user" else \
        data.get("projects", {}).get(str(workspace), {}).get("mcpServers", {})
    return (servers.get("tubematic") or {}).get("headersHelper") == auth.helper


def _agent_checks(agent: dict) -> list:
    """What --install-agent set up for one agent, re-checked on disk.

    Driven off the agent's adapter rather than Claude's layout: checking
    ~/.claude for a Codex install reported skills that were never there and
    warned, forever, about commands, an allowlist and a trust record that Codex
    deliberately does not have.
    """
    # Deferred: agent_install imports onboard.actions, which imports this module.
    from onboard.agent_install import ADAPTERS, config_root_conflict

    aid = agent["id"]
    hint = f"re-run: python onboard.py --install-agent {aid}"
    binary = agent.get("binary") or ""
    ws = Path(agent.get("run_path") or "").expanduser()
    adapter = ADAPTERS.get(aid)
    items = [
        CheckItem(f"[{aid}] binary in PATH ({binary})", bool(shutil.which(binary)),
                  hint=f"install it, then {hint}"),
        CheckItem(f"[{aid}] models validated", bool(agent.get("models")), severity="warning",
                  hint=f"no models stored — {hint}"),
    ]
    if adapter is None:
        items.append(CheckItem(f"[{aid}] supported by this version", False, severity="warning",
                               hint="this version has no adapter for that agent"))
        return items

    if agent.get("install_scope") == "project":
        skills_root = adapter.project_skills_dir(ws)
        mcp_config = getattr(adapter, "mcp_config_file", None)
        config = mcp_config(Path.home(), ws, "project") if mcp_config else None
        registered = _mcp_registered_in_config(adapter, config) \
            if config else _mcp_registered_project(ws)
        items += [
            CheckItem(f"[{aid}] workspace skills installed",
                      (skills_root / _PROOF_SKILL).is_dir(), hint=hint),
            CheckItem(f"[{aid}] MCP registered (workspace)", registered, hint=hint),
        ]
        if config is not None:
            items.append(_mcp_options_check(aid, adapter, ws, hint))
    else:
        home = Path.home()
        # respect_override=False: this is a read-only diagnostic, and what it
        # must describe is the root the SCHEDULED runs use. Cron never inherits
        # an environment override, so resolving one here would report a
        # perfectly good install as missing its skills and send the user off to
        # re-run an install that was already correct.
        skills_root = adapter.user_skills_dir(home, respect_override=False)
        items.append(CheckItem(f"[{aid}] user skills installed ({skills_root})",
                               (skills_root / _PROOF_SKILL).is_dir(), hint=hint))
        if adapter.HAS_COMMANDS:
            commands_root = adapter.user_commands_dir(home)
            items.append(CheckItem(f"[{aid}] user commands installed ({commands_root})",
                                   bool(commands_root) and commands_root.is_dir(), hint=hint))
        mcp_config = getattr(adapter, "mcp_config_file", None)
        # respect_override=False for the same reason the skills root above uses
        # it: this describes the install a SCHEDULED run will see, and cron
        # never inherits an environment override.
        config = mcp_config(home, ws, "user", False) if mcp_config else None
        registered = _mcp_registered_in_config(adapter, config) \
            if config else _mcp_registered_user(binary)
        items.append(CheckItem(f"[{aid}] MCP registered (user scope)", registered, hint=hint))
        if config is not None:
            items.append(_mcp_options_check(aid, adapter, ws, hint))
    items.append(CheckItem(f"[{aid}] MCP token wired into its registration",
                           _mcp_auth_wired(adapter, agent, ws),
                           hint=f"the MCP server will refuse this agent (401) — {hint}"))
    items.append(CheckItem(f"[{aid}] workspace exists ({ws})", ws.is_dir(), hint=hint))
    # Reported rather than silently worked around: the checks above describe
    # the default root, but this shell's CLI would use a different one, so the
    # two disagree and every other result here needs that context to read right.
    conflict = config_root_conflict(adapter)
    if conflict:
        items.append(CheckItem(f"[{aid}] {conflict[0]}", False, hint=conflict[1]))
    if adapter.NEEDS_PERMISSION_CONFIG:
        # Tubematic writes every basename OpenCode loads, because whichever it
        # loads last wins. A MISSING one reopens that slot for a document that
        # would outrank every rule in ours — so the check is that they are all
        # there, which `workspace permissions` alone would not notice.
        missing = [p for p in adapter.managed_config_files(ws) if not p.is_file()]
        items.append(CheckItem(
            f"[{aid}] every loaded config is Tubematic's ({adapter.managed_config_file(ws).parent})",
            not missing,
            hint=f"missing {', '.join(p.name for p in missing)} — a file at that name would be "
                 f"loaded after Tubematic's and override its rules; {hint}"))
        items.append(CheckItem(
            f"[{aid}] workspace permissions ({adapter.managed_config_file(ws)})",
            _has_permission_rules(adapter, ws), hint=hint))
    if adapter.NEEDS_ALLOWLIST:
        items += [
            CheckItem(f"[{aid}] allowlist (mcp__tubematic)",
                      _has_allowlist(ws / ".claude" / "settings.json"), hint=hint),
            CheckItem(f"[{aid}] data directory denied to Read ({DATA_ROOT})",
                      _has_data_dir_deny(ws / ".claude" / "settings.json"), hint=hint),
            CheckItem(f"[{aid}] workspace trusted (headless permissions apply)", _has_trust(ws),
                      hint=hint),
        ]
    items += [
        CheckItem(f"[{aid}] poll logs directory exists ({POLL_LOG_DIR})", POLL_LOG_DIR.is_dir(),
                  hint=hint),
        # The Remotion installer writes to the agent's own skills root for some
        # agents and to the shared ~/.agents/skills root for others, and both
        # are read, so either location counts as installed.
        CheckItem(f"[{aid}] remotion-best-practices skill installed",
                  any((root / "remotion-best-practices" / "SKILL.md").exists()
                      for root in (skills_root, Path.home() / ".agents" / "skills")),
                  hint=f"requires Node >= 22 — {hint}"),
    ]
    return items


def check_installation() -> dict:
    """Returns {"SERVICES": [CheckItem, ...], "AGENT": [CheckItem, ...]}."""
    import sqlite3
    import sys

    settings = read_settings(DB_PATH)

    services: list = []
    services.append(CheckItem("Python 3.11+", sys.version_info >= (3, 11)))
    services.append(CheckItem("Docker running", _run(["docker", "info"]).returncode == 0))
    services.append(CheckItem("Settings: ElevenLabs API key",
                               bool(settings.get("elevenlabs_api_key")),
                               hint="add it on the Settings dashboard, or re-run: "
                                    "python onboard.py --step install_config"))
    services.append(CheckItem("Settings: Gemini API key",
                               bool(settings.get("gemini_api_key")), severity="warning",
                               hint="optional — without it mining and AI review are off; add it "
                                    "on the Settings dashboard to turn them on"))
    # Scene images need the OpenAI key (TMDEV-165). Error severity so it stands
    # out on the verify screen; the actual gate is the rep.fail in
    # actions.apply_install_config, since print_verify only reports.
    services.append(CheckItem("Settings: OpenAI API key",
                               bool(settings.get("openai_api_key")),
                               severity="error",
                               hint="required for scene images — re-run: python onboard.py "
                                    "--step install_config"))

    # Flask and MCP are separate containers with separate healthchecks, so
    # they are reported separately: a healthy Flask says nothing about whether
    # the agent's tools are reachable, and vice versa.
    r = subprocess.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", "tubematic-api"],
                        capture_output=True, text=True)
    services.append(CheckItem("API container healthy", r.stdout.strip() == "healthy",
                               hint="docker compose up -d tubematic-api"))

    r_mcp = subprocess.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", "tubematic-mcp"],
                            capture_output=True, text=True)
    services.append(CheckItem("MCP container healthy", r_mcp.stdout.strip() == "healthy",
                               hint="docker compose up -d tubematic-mcp"))

    r_worker = subprocess.run(["docker", "inspect", "--format", "{{.State.Status}}", "tubematic-renderer"],
                               capture_output=True, text=True)
    services.append(CheckItem("Render worker container running", r_worker.stdout.strip() == "running",
                               hint="docker compose up -d tubematic-renderer"))

    r2 = subprocess.run(["docker", "inspect", "--format", "{{.State.Status}}", "tubematic-dashboard"],
                         capture_output=True, text=True)
    services.append(CheckItem("Dashboard container running", r2.stdout.strip() == "running",
                               hint="docker compose up -d tubematic-dashboard"))

    services.append(CheckItem("Database exists", DB_PATH.exists()))

    settings_seeded = False
    if DB_PATH.exists():
        try:
            c = sqlite3.connect(str(DB_PATH))
            settings_seeded = c.execute("SELECT 1 FROM settings WHERE key='trending_sources'").fetchone() is not None
            c.close()
        except Exception:
            settings_seeded = False
    services.append(CheckItem("Pipeline settings seeded", settings_seeded,
                               hint="python onboard.py --step pipeline_settings"))
    services.extend(auth_items())
    refused, accepted = mcp_auth_probe()
    if refused is not None:
        services.append(CheckItem("MCP refuses a request without the token", refused,
                                  hint="the MCP server is running without auth — rebuild and "
                                       "restart it: python upgrade.py"))
    if accepted is not None:
        services.append(CheckItem("MCP accepts the install's token", accepted,
                                  hint="the server holds an older token — "
                                       "docker compose restart tubematic-mcp"))

    # One group of checks per live agent (TMDEV-90). None installed is a
    # warning, not an error: it is a valid intermediate state — the project
    # works, cron just logs "No agent installed" each tick until one exists.
    agent_items: list = []
    live = [a for a in read_agents(DB_PATH) if not a.get("archived_at")]
    if not live:
        agent_items.append(CheckItem(
            "Agent installed", False, severity="warning",
            hint="nothing runs until one is: python onboard.py --install-agent <agent>"))
    for agent in live:
        agent_items.extend(_agent_checks(agent))
    if live:
        from onboard.agent_install import mcp_auth
        agent_items.append(CheckItem(
            "MCP header helper prints the token", _helper_prints_a_header(mcp_auth().helper),
            hint="python onboard.py --step auth, then re-run --install-agent for each agent"))

    r3 = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    agent_items.append(CheckItem("Cron entries written", r3.returncode == 0 and "poll.py" in r3.stdout,
                                  hint="see docs/user-guide/02-installing.md -> Manual cron setup"))

    return {"SERVICES": services, "AGENT": agent_items}
