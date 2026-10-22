"""The 12 apply-phase actions.

Each `apply_*` function takes `(cfg: OnboardConfig, ex: Executor, rep: Reporter)`
and performs one step's mutations, reading answers from `cfg.values` instead
of prompting (prompting happens earlier, on the Configure screen). All
mutations route through `ex` so dry-run is a property of the Executor, not
something threaded through every function individually.

The agent-deployment helpers (`_install_remotion_skills`,
`_write_agent_allowlist`, `_write_agent_trust`, `_copy_skills`,
`_copy_commands`, `_register_mcp`) are no longer a step of their own: they are
called by onboard/agent_install.py, i.e. `onboard.py --install-agent <name>`
(TMDEV-90). They keep their original call signature with `ex`/`rep` as
optional keyword args defaulting to a live executor and a discarding reporter
— TMDEV-39's verification called these directly inside a `docker run` probe,
and that must keep working unchanged.
"""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from onboard.config import (REPO_ROOT, DB_PATH, DATA_ROOT, POLL_LOG_DIR, OnboardConfig,
                            detect_install_mode)
from onboard.executor import Executor, Reporter, NullReporter
from tubematic_core import db as tdb


def _live_ex() -> Executor:
    return Executor(dry_run=False)


def _compose() -> list:
    """The `docker compose` argv prefix — the one place apply_renderer,
    apply_dashboard and _reconcile_volume_devices read it from, so they
    cannot disagree about which compose file they're talking to. The
    release tarball's compose file is named identically
    (docker-compose.yml), so this never needs a -f flag; the difference
    between dev and release installs is the actions run, not the file."""
    return ["docker", "compose"]


def _install_mode(cfg: OnboardConfig | None) -> str:
    """Resolve the effective install mode for an apply_* action.

    cfg carries the answer run_wizard already resolved and reported
    (cfg.values["install_mode"]) so every action agrees with it. cfg is
    None in a few tests that call apply_renderer/apply_dashboard directly
    — auto-detecting from the checkout layout is the same thing a real run
    with no --install-mode override would do."""
    if cfg is not None:
        explicit = cfg.values.get("install_mode")
        if explicit:
            return explicit
    return detect_install_mode()


# ── Settings-table helpers ───────────────────────────────────────────────────

def _ensure_db_writable(ex: Executor, rep: Reporter) -> bool:
    """Repair root-owned tubematic.db* left by a prior install's containers.

    The Prereq screen already surfaces this (read-only os.stat) with the exact
    `sudo chown` command; here we only attempt the plain chown (works when the
    current user already owns the files, or when running as root) and fail
    loudly with the same hint otherwise — no interactive sudo prompt mid-apply,
    since suspending the terminal from inside a worker thread is fragile.

    Returns False when the caller should stop. Shared by the two steps that
    write settings rows (TMDEV-73 gave install_config the same need).
    """
    target = f"{os.getuid()}:{os.getgid()}"
    for f in sorted(DB_PATH.parent.glob("tubematic.db*")):
        try:
            owned = f.stat().st_uid == os.getuid()
        except OSError:
            continue
        if owned:
            continue
        try:
            ex.chown(f, os.getuid(), os.getgid())
        except PermissionError:
            rep.fail(f"Cannot fix ownership of {f.name}.", hint=f"Run manually: sudo chown {target} {f}")
            return False
    return True


def _upsert_settings(ex: Executor, rows: dict, detail: str) -> None:
    """Write every key in `rows` to the settings table in one Executor intent."""
    def _write(con):
        for key, value in rows.items():
            con.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
    ex.sqlite_write(DB_PATH, _write, detail)


# ── Step 1: Prerequisites ───────────────────────────────────────────────────

def apply_prerequisites(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    from onboard.checks import check_prerequisites
    errors = []
    for item in check_prerequisites(mode=_install_mode(cfg)):
        if item.ok:
            rep.ok(item.label)
        elif item.severity == "warning":
            rep.warn(f"{item.label} — {item.hint}" if item.hint else item.label)
        else:
            errors.append(item)
    if errors:
        rep.fail(
            "; ".join(i.label for i in errors),
            hint="See docs/user-guide/02-installing.md → Prerequisites.",
        )


# ── Step 5: Install configuration ────────────────────────────────────────────

def apply_install_config(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    """Seed the settings table with the install's configuration.

    Runs after `database` — there has to be a table to write into. This is the
    only step that persists credentials; they are stored raw, and masked by the
    settings API so the dashboard never receives one (TMDEV-73).
    """
    if not DB_PATH.exists():
        rep.warn("Database not initialised — run --step database first.")
        return
    if not _ensure_db_writable(ex, rep):
        return

    from onboard.config import ENV_FIELD_TO_SETTING

    v = cfg.values
    mcp_port = v.get("MCP_PORT", "4100")

    # RENDERER_URL and MCP_URL are not stored: everything runs on one machine
    # and compose publishes fixed ports, so they were never configurable in
    # practice. They are in-code constants.
    values = {
        "ELEVENLABS_API_KEY": v.get("ELEVENLABS_API_KEY", ""),
        "GEMINI_API_KEY": v.get("GEMINI_API_KEY", ""),
        "OPENAI_API_KEY": v.get("OPENAI_API_KEY", ""),
        "YOUTUBE_TRANSCRIPT_API_KEY": v.get("YOUTUBE_TRANSCRIPT_API_KEY", ""),
        # Keep the "false" in sync with PUBLISHING_ENABLED's field default —
        # this fallback is a second copy of it, and drift the wrong way would
        # silently turn publishing on for an install that never answered.
        "POSTFORME_API_KEY": v.get("POSTFORME_API_KEY", ""),
        "PUBLISHING_ENABLED": v.get("PUBLISHING_ENABLED", "false"),
        # Keep the "false" in sync with GEMINI_REVIEW_ENABLED's field default.
        "GEMINI_REVIEW_ENABLED": v.get("GEMINI_REVIEW_ENABLED", "false"),
        "MAX_RENDER_RETRIES": v.get("MAX_RENDER_RETRIES", "1"),
        "RESEARCH_PENDING_CAP": v.get("RESEARCH_PENDING_CAP", "15"),
        "MCP_PORT": mcp_port,
    }

    rows = {ENV_FIELD_TO_SETTING[k]: val for k, val in values.items()}

    try:
        _upsert_settings(ex, rows, "seed install configuration")
    except Exception as e:
        rep.fail(f"Install configuration seeding failed: {e}")
        return

    rep.ok("Install configuration seeded into settings table")
    rep.info("API keys are editable later on the Settings dashboard — they are never displayed "
             "there in full, only as a masked hint.")

    # Scene images need the OpenAI key: OpenAI is the only image provider
    # (TMDEV-165). This is the backstop that keeps --allow-skipping safe — the
    # prompt's own required check is off under that flag. Checked after the
    # write deliberately: rep.fail raises, which aborts the wizard without
    # marking this step done — so it re-prompts on re-run, and everything
    # already typed is stored to pre-fill it.
    # The error-severity CheckItem in checks.py is only for the verify screen;
    # print_verify never blocks, so this is the block.
    if not values["OPENAI_API_KEY"]:
        rep.fail(
            "No OpenAI API key configured.",
            hint="Scene images come from OpenAI, so the key is required. "
                 "Re-run: python onboard.py --step install_config",
        )


# ── Step 3: Python dependencies ──────────────────────────────────────────────

def apply_python_deps(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    req = REPO_ROOT / "scripts" / "requirements.txt"
    if not req.exists():
        rep.warn(f"{req.relative_to(REPO_ROOT)} not found — skipping")
        return
    r = ex.run([sys.executable, "-m", "pip", "install", "-q", "-r", str(req)], cwd=REPO_ROOT)
    if r.returncode != 0:
        rep.fail(f"pip install failed for {req.relative_to(REPO_ROOT)}", "Check your Python environment.")
        return
    rep.ok("scripts/ packages installed")


# ── Step 4: Directories ──────────────────────────────────────────────────────

def apply_directories(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    # ~/.tubematic-data, not a repo-relative mounted/ (TMDEV-76): this is
    # machine state, and living inside the checkout meant a re-clone destroyed
    # the video library and the database. Created here, before any container
    # starts — docker-compose.yml declares these as named `local`-driver,
    # `o: bind` volumes, and for that kind of volume Docker does NOT
    # auto-create a missing device path: the mount fails outright with "no
    # such file or directory" (verified directly, not inferred — see
    # TMDEV-91's release smoke test, which hits exactly this on a fresh
    # runner and creates these same directories itself for that reason).
    # Auto-create-as-root-then-unwritable is real, but only for a
    # short-syntax host bind (`- ./path:/container/path`), which this
    # project uses nowhere.
    from onboard.config import DATA_ROOT, DATA_SUBDIRS
    for d in DATA_SUBDIRS:
        path = DATA_ROOT / d
        ex.mkdir(path)
        rep.ok(str(path))


# ── Step 5: Database ──────────────────────────────────────────────────────────

def apply_database(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    """Create or migrate the pipeline database.

    Runs before any container starts, for the same root-ownership reason as the
    directories step. The schema lives in tubematic_core/migrations/ (TMDEV-91);
    this function used to hold a fourth copy of it, which had already gone stale
    on six columns and three tables.

    Not routed through ex.sqlite_write: that helper hands a callback one
    connection and commits it, while migrate() owns its own connection and one
    transaction per migration. The dry-run branch records the intent instead.
    """
    ex.mkdir(DB_PATH.parent)

    if ex.dry_run:
        rep.info(f"[dry-run] would migrate {DB_PATH} to the latest schema")
        return

    try:
        result = tdb.migrate(DB_PATH)
    except Exception as e:
        rep.fail(f"Database migration failed: {e}")
        return

    if result.backup_path:
        rep.info(f"Backed up to {result.backup_path}")
    if result.applied:
        rep.ok(f"{DB_PATH} migrated to schema {result.to_version:04d} "
               f"({len(result.applied)} applied)")
    else:
        rep.ok(f"{DB_PATH} already at schema {result.to_version:04d}")


# ── Dashboard password and service tokens (TMDEV-152) ────────────────────────

def apply_auth(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    """Create any missing service token, then ask for the dashboard password
    when none is set.

    Before the container steps on purpose: Compose refuses to start a service
    whose secret file is missing. Asks only when no password exists, so a
    re-run never silently changes it — that is `--set-password`'s job.
    """
    from tubematic_core import auth
    created = ex.ensure_secrets()
    if not ex.dry_run:
        rep.ok(f"Service tokens in {auth.secrets_dir()}"
               + (f" (created {', '.join(created)})" if created else " (kept)"))
    if auth.has_admin_password(DB_PATH):
        rep.ok("Dashboard password already set — change it with: python onboard.py --set-password")
        return
    if ex.dry_run:
        rep.info("[dry-run] would ask for the dashboard password")
        return
    from onboard.prompt import ask_new_password
    password = ask_new_password()
    _upsert_settings(ex, {auth.PASSWORD_KEY: auth.hash_password(password)},
                     "the dashboard password (its hash only)")
    rep.ok("Dashboard password set")


# ── Step 6: Pipeline settings ─────────────────────────────────────────────────

def _clamp_nonneg_int(raw: str, fallback: str) -> str:
    try:
        return str(max(0, int(raw)))
    except (ValueError, TypeError):
        return fallback


def _clamp_min_1_int(raw: str, fallback: str) -> str:
    try:
        return str(max(1, int(raw)))
    except (ValueError, TypeError):
        return fallback


def _clamp_range_int(raw: str, fallback: str, low: int, high: int) -> str:
    try:
        return str(max(low, min(high, int(raw))))
    except (ValueError, TypeError):
        return fallback


def apply_pipeline_settings(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    if not DB_PATH.exists():
        rep.warn("Database not initialised — run --step database first.")
        return

    if not _ensure_db_writable(ex, rep):
        return

    v = cfg.values
    # Both fallbacks are copies of GEMINI_REVIEW_ENABLED's field default; a
    # skipped or garbled answer must land on off, never silently on.
    review = v.get("GEMINI_REVIEW_ENABLED", "false").strip().lower()
    review = review if review in ("true", "false") else "false"
    retries = _clamp_nonneg_int(v.get("MAX_RENDER_RETRIES", "1"), "1")
    cap = _clamp_nonneg_int(v.get("RESEARCH_PENDING_CAP", "15"), "15")

    # Voice roster (TMDEV-51) — purely DB-backed, like every other field in
    # this section. A fresh install gets voice_models.DEFAULT_VOICES through
    # the field's default (TMDEV-172); a re-run carries the stored roster,
    # since load_current_values prefers it, and leaving the "voices" prompt
    # blank keeps it unchanged (see onboard/prompt.py).
    from onboard.config import _parse_voices
    voices = _parse_voices(v.get("elevenlabs_voices", "[]"))
    roster_ids = {voice["voice_id"] for voice in voices}
    default_voice = v.get("elevenlabs_voice_id", "")
    if default_voice not in roster_ids:
        default_voice = voices[0]["voice_id"] if voices else ""

    cur = _clamp_nonneg_int(v.get("max_curriculum_per_run", "2"), "2")
    trend = _clamp_nonneg_int(v.get("max_trending_per_run", "2"), "2")
    mine = _clamp_nonneg_int(v.get("max_mining_per_run", "2"), "2")
    max_research_runs = _clamp_nonneg_int(v.get("max_research_runs_per_day", "8"), "8")

    sources_raw = v.get("trending_sources", "")
    try:
        sources = json.loads(sources_raw) if sources_raw else []
    except (json.JSONDecodeError, TypeError):
        sources = []
    if not sources:
        from onboard.config import DEFAULT_TRENDING_SOURCES
        sources = DEFAULT_TRENDING_SOURCES

    from onboard.config import (
        DEFAULT_IMAGE_MODEL, OPENAI_IMAGE_MODELS,
        AI_REVIEW_MODELS, DEFAULT_AI_REVIEW_MODEL,
        MAX_AI_REVIEW_FPS, MAX_AI_REVIEW_LOOPS,
    )
    image_model = v.get("image_model", DEFAULT_IMAGE_MODEL)
    # The settings API allowlists image_model, so seeding anything else here
    # would leave the dashboard 400ing on the next save of that key.
    if image_model not in OPENAI_IMAGE_MODELS:
        image_model = DEFAULT_IMAGE_MODEL

    # Asked in minutes (onboard/config.py's render_timeout_mins field); stored
    # in seconds, which is what renderer/api/pipeline.py's SETTINGS_SPEC and
    # worker.py actually read (TMDEV-57). render_timeout_mins is never itself
    # a settings-table key.
    timeout_mins = _clamp_min_1_int(v.get("render_timeout_mins", "40"), "40")
    render_timeout_secs = str(int(timeout_mins) * 60)

    # AI review (VQA-7). Clamped rather than trusted for the same reason the
    # image pair above is: the settings API validates these, so seeding an
    # out-of-range value would leave the dashboard 400ing on the next save.
    ai_review_model = v.get("ai_review_model", DEFAULT_AI_REVIEW_MODEL)
    if ai_review_model not in AI_REVIEW_MODELS:
        ai_review_model = DEFAULT_AI_REVIEW_MODEL
    from onboard.config import MAX_LOG_RETENTION_DAYS, MIN_LOG_RETENTION_DAYS
    log_retention_days = _clamp_range_int(
        v.get("log_retention_days", "14"), "14",
        MIN_LOG_RETENTION_DAYS, MAX_LOG_RETENTION_DAYS)
    # The "7" fallback is a second copy of the field default and SETTINGS_SPEC's
    # — a skipped (advanced) question lands here, so it must match both.
    from onboard.config import MAX_RETENTION_DAYS, MIN_RETENTION_DAYS
    retention_days = _clamp_range_int(
        v.get("retention_days", "7"), "7", MIN_RETENTION_DAYS, MAX_RETENTION_DAYS)

    # Anything but an explicit "true" is off: this switch removes every human
    # checkpoint, so a malformed answer must never read as yes.
    auto_pilot_enabled = (
        "true" if str(v.get("auto_pilot_enabled", "false")).lower() == "true" else "false")

    ai_review_fps = _clamp_range_int(v.get("ai_review_fps", "10"), "10", 1, MAX_AI_REVIEW_FPS)
    ai_review_max_loops = _clamp_range_int(
        v.get("ai_review_max_loops", "1"), "1", 1, MAX_AI_REVIEW_LOOPS)

    rows = {
        "gemini_review_enabled": review,
        "max_render_retries": retries,
        "max_curriculum_per_run": cur,
        "max_trending_per_run": trend,
        "max_mining_per_run": mine,
        "research_pending_cap": cap,
        "max_research_runs_per_day": max_research_runs,
        "trending_sources": json.dumps(sources),
        "elevenlabs_voices": json.dumps(voices),
        "elevenlabs_voice_id": default_voice,
        "image_model": image_model,
        "render_timeout_secs": render_timeout_secs,
        "ai_review_model": ai_review_model,
        "ai_review_fps": ai_review_fps,
        "ai_review_max_loops": ai_review_max_loops,
        "log_retention_days": log_retention_days,
        "retention_days": retention_days,
        "auto_pilot_enabled": auto_pilot_enabled,
    }

    def _write(con):
        for key, value in rows.items():
            con.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
        con.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('pipeline_paused', 'false')")
        con.execute(
            "INSERT OR IGNORE INTO settings (key, value) VALUES "
            "('active_strategies', 'curriculum,trending,mining')"
        )

    try:
        ex.sqlite_write(DB_PATH, _write, "seed pipeline settings")
        rep.ok("Pipeline settings seeded into settings table")
        rep.info("These are editable later on the Settings dashboard — no need to re-run this step.")
    except Exception as e:
        rep.fail(f"Pipeline settings seeding failed: {e}")


# ── Agent deployment helpers (used by onboard/agent_install.py) ──────────────

def _copy_skills(src_skills: Path, dest_skills: Path, label: str, *,
                  ex: Executor = None, rep: Reporter = None) -> int:
    ex = ex or _live_ex()
    rep = rep or NullReporter()
    if not src_skills.exists():
        rep.warn(f"Skills source not found: {src_skills}")
        return 0
    ex.mkdir(dest_skills)
    count = 0
    for skill_dir in src_skills.iterdir():
        if skill_dir.is_dir():
            ex.copytree(skill_dir, dest_skills / skill_dir.name)
            count += 1
    rep.ok(f"{count} skills → {label}")
    return count


def _copy_commands(src_cmds: Path, dest_cmds: Path, label: str, agent: str, *,
                    ex: Executor = None, rep: Reporter = None) -> int:
    ex = ex or _live_ex()
    rep = rep or NullReporter()
    if not src_cmds.exists():
        rep.warn(f"No commands found for agent '{agent}' in agent_files/{agent}/commands/")
        return 0
    ex.mkdir(dest_cmds)
    count = 0
    for f in src_cmds.glob("*.md"):
        ex.copy_file(f, dest_cmds / f.name)
        count += 1
    rep.ok(f"{count} commands → {label}")
    return count


def claude_read_denies() -> list:
    """The Read deny rules Claude's workspace allowlist carries.

    The agent may read almost anything, but not the data directory: it holds
    the database (every API key since keys moved into the settings table) and
    `secrets/` (the service tokens and the password hash). Reading the poll
    logs, which live under ~/.tubematic-agent, is unaffected. The MCP token
    still reaches Claude Code: its `headersHelper` is a separate process that
    reads the file itself, not a Read tool call.

    Claude Code's path syntax, per its permissions docs: `//path` is absolute
    from the filesystem root and `~/path` is from the home directory. A single
    leading slash is NOT absolute — it anchors at the settings file's own
    project — so `Read(/home/...)` here would deny nothing. A Read rule also
    covers Grep and Glob. Both forms are written when the directory is under
    home; they name the same place, and either alone is enough.
    """
    denies = [f"Read(/{DATA_ROOT}/**)"]
    try:
        denies.append(f"Read(~/{DATA_ROOT.relative_to(Path.home()).as_posix()}/**)")
    except ValueError:
        pass
    return denies


def _write_agent_allowlist(workspace: Path, *, ex: Executor = None, rep: Reporter = None) -> None:
    """Merge mcp__tubematic + WebFetch/WebSearch/Read/Glob/Grep into
    workspace/.claude/settings.json, deny Read on the data directory, then
    mark the workspace trusted.

    Kept directly callable with the same signature as before (TMDEV-39's
    verification calls this inside a `docker run` probe) — ex/rep are
    optional and default to live execution."""
    ex = ex or _live_ex()
    rep = rep or NullReporter()

    settings_dir = workspace / ".claude"
    ex.mkdir(settings_dir)
    settings_path = settings_dir / "settings.json"

    existing: dict = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text())
        except Exception:
            pass

    perms = existing.setdefault("permissions", {})
    allow = perms.setdefault("allow", [])
    for entry in ("mcp__tubematic", "WebFetch", "WebSearch", "Read", "Glob", "Grep"):
        if entry not in allow:
            allow.append(entry)
    # The poll logs sit beside every workspace, never inside one, and the agent
    # prompts tell the agent to read poll.log when something goes wrong. The
    # unscoped "Read" above already reaches it (verified live); this keeps it
    # readable if Read is ever narrowed to the workspace.
    extra_dirs = perms.setdefault("additionalDirectories", [])
    if str(POLL_LOG_DIR) not in extra_dirs:
        extra_dirs.append(str(POLL_LOG_DIR))
    # A deny beats any allow in Claude Code whatever the order, so merging is
    # enough here (contrast OpenCode's last-match-wins below).
    deny = perms.setdefault("deny", [])
    for entry in claude_read_denies():
        if entry not in deny:
            deny.append(entry)

    ex.write_file(settings_path, json.dumps(existing, indent=2) + "\n")
    rep.ok(f"Agent allowlist → {settings_path}")

    _write_agent_trust(workspace, ex=ex, rep=rep)


def _read_agent_config(adapter, path: Path, rep: Reporter) -> tuple:
    """`(data, original_text)` for an agent's config document.

    `data` is `{}` when the file is absent and `None` when it exists but cannot
    be read — a refusal to guess, because a document that exists belongs to
    somebody and replacing it with a fresh one would delete their settings.
    Parsing goes through the adapter, because an agent's config may be JSONC:
    OpenCode accepts comments and trailing commas in a plain `.json`, so
    `json.loads` alone would report a perfectly valid config as broken and have
    the installer skip the permission rules.
    """
    if not path.exists():
        return {}, ""
    original = path.read_text()
    try:
        data = adapter.parse_config(original)
    except Exception:
        rep.warn(f"Could not parse {path} — leaving it alone; fix it by hand and re-run")
        return None, original
    return (data if isinstance(data, dict) else None), original


def managed_rules_last(existing, managed: list) -> list:
    """`existing` with every managed rule moved to the end, in the given order.

    Appending only the missing rules is not enough, and the gap is exploitable:
    OpenCode resolves permissions **last match wins**, so a rule already in the
    file followed by a later contradicting one leaves the later one in force
    while a membership test still says the managed rule is present. Verified —
    a `read *.env deny` followed by a `read *.env allow` read the file. Moving
    them to the end makes the managed rules authoritative whatever else the
    document contains.
    """
    kept = [r for r in existing if r not in managed] if isinstance(existing, list) else []
    return kept + [dict(r) for r in managed]


def managed_permission_rules(adapter) -> list:
    """The rules this agent's install asserts, in the order they must appear.

    Shared with the post-install check, so the check cannot drift from what the
    installer writes — which is how a check that passes on a broken install
    gets written.
    """
    rules = [dict(r) for r in adapter.PERMISSION_RULES]
    # The poll logs sit beside every workspace, never inside one, and the agent
    # prompts tell the agent to read poll.log when something goes wrong.
    # Reaching outside the working directory is a permission of its own here,
    # so it is granted explicitly rather than left to the auto-approval on argv
    # — the same reason Claude's allowlist names the directory instead of
    # relying on an unscoped Read.
    rules.append({"action": "external_directory",
                  "resource": f"{POLL_LOG_DIR}/*", "effect": "allow"})
    # The data directory holds the database (every API key) and the service
    # tokens, and is never the agent's to read. These come LAST so they win
    # over `read * allow` above — permissions resolve last-match-wins. Two
    # rules, because OpenCode's grep and glob are checked against the search
    # PATTERN, not a path, so a read deny alone cannot stop them; reaching
    # outside the workspace is the separate `external_directory` permission,
    # and denying it there is what keeps them out. The workspace is
    # ~/.tubematic-agent, so the data directory is always external. The MCP
    # token still reaches OpenCode: `{file:...}` is resolved when the config
    # loads, not through a tool.
    rules.append({"action": "external_directory",
                  "resource": f"{DATA_ROOT}/**", "effect": "deny"})
    rules.append({"action": "read", "resource": f"{DATA_ROOT}/**", "effect": "deny"})
    return rules


def _write_agent_permissions(adapter, workspace: Path, mcp_url: str, auth, *,
                             ex: Executor = None, rep: Reporter = None) -> None:
    """Everything this agent's install asserts, in one document Tubematic owns.

    The counterpart of `_write_agent_allowlist` for an agent configured by
    file. Three properties, each of which was a defect before it was one:

    - **It is written into the agent's own managed document**, never into one
      the operator wrote. So there is no case where the installer has to choose
      between deleting somebody's comments and skipping a security rule — it
      simply always writes, and the install can never complete unrestricted.
    - **That document outranks every other**, so a rule here cannot be
      overridden by a global or ancestor config. See the adapter for the
      measured precedence order.
    - **The managed rules are re-asserted at the end** of whatever the document
      already holds. Permissions resolve last-match-wins, so appending only the
      missing ones would leave a later contradicting rule in force while a
      membership test still reported the rule as present.

    The MCP server entry is written COMPLETE (type, url and options) for a
    reason the adapter documents: an options-only entry connects but does not
    apply its options. `opencode mcp add` still runs separately, so the server
    is also registered for interactive sessions outside the workspace — that
    registration is the operator's file, and this never edits it.
    """
    ex = ex or _live_ex()
    rep = rep or NullReporter()

    path = adapter.managed_config_file(workspace)
    wanted = managed_permission_rules(adapter)
    existing, _ = _read_agent_config(adapter, path, rep)
    if existing is None:
        # Ours, and unreadable — replacing it is right, because the only thing
        # it can hold is a previous copy of what is about to be written.
        rep.warn(f"{path} could not be read and is Tubematic's own — rewriting it")
        existing = {}
    existing["permissions"] = managed_rules_last(existing.get("permissions"), wanted)
    servers = existing.setdefault("mcp", {}).setdefault("servers", {})
    servers["tubematic"] = adapter.mcp_server_entry(mcp_url, auth)
    ex.mkdir(path.parent)
    # Every basename OpenCode loads, identical content. Whichever it reads
    # last is Tubematic's, so nothing can be dropped in beside ours to
    # outrank it — see the adapter for the measurement.
    written = adapter.managed_config_files(workspace)
    body = json.dumps(existing, indent=2) + "\n"
    for target in written:
        ex.write_file(target, body)
    rep.ok(f"Agent permissions and tool options → {', '.join(t.name for t in written)} "
           f"in {path.parent}")


def _write_agent_trust(workspace: Path, *, ex: Executor = None, rep: Reporter = None) -> None:
    ex = ex or _live_ex()
    rep = rep or NullReporter()

    claude_json_path = Path.home() / ".claude.json"
    data: dict = {}
    if claude_json_path.exists():
        try:
            data = json.loads(claude_json_path.read_text())
        except Exception:
            rep.warn(f"Could not parse {claude_json_path} — skipping trust setup; "
                      f"run Claude Code interactively in {workspace} once to trust it manually")
            return

    projects = data.setdefault("projects", {})
    entry = projects.setdefault(str(workspace), {})
    entry.setdefault("hasTrustDialogAccepted", True)
    entry.setdefault("allowedTools", [])
    entry.setdefault("mcpServers", {})

    ex.write_file(claude_json_path, json.dumps(data, indent=2) + "\n")
    rep.ok(f"Agent workspace trusted → {claude_json_path}")


def _register_mcp(argv: list, cwd: Path, label: str, mcp_url: str, *,
                   ex: Executor = None, rep: Reporter = None) -> None:
    """Register the tubematic MCP server using the agent's own argv.

    The argv comes from the adapter being installed, built around the binary
    `check_preconditions` already resolved — never whatever the PATH happens to
    find first, which on a machine with two agents installed is a real hazard.
    The manual-retry hint is that same argv rather than a second hand-written
    copy of it, which is how the two used to drift.
    """
    ex = ex or _live_ex()
    rep = rep or NullReporter()

    r = ex.run(argv, cwd=cwd)
    if r.returncode == 0:
        rep.ok(f"MCP server registered ({label})")
    else:
        rep.warn(f"MCP registration failed: {(r.stderr or '').strip()}")
        rep.warn(f"Register manually: {' '.join(argv)}")
    rep.info(f"  url: {mcp_url}")


def _patch_mcp_header_helper(adapter, auth, *, ex: Executor = None, rep: Reporter = None) -> None:
    """Set the header helper in a config the CLI's own `mcp add` cannot reach.

    Codex's `mcp add` has no header flag and drops any key it does not set, so
    this runs after every add (TMDEV-152). The result is parsed before it is
    written: a document this edit broke would stop the CLI starting at all.
    """
    import tomllib
    ex = ex or _live_ex()
    rep = rep or NullReporter()
    path = adapter.config_toml()
    if ex.dry_run:
        rep.info(f"[dry-run] would set the MCP header helper in {path}")
        return
    try:
        text = path.read_text()
    except OSError:
        text = ""
    edited = adapter.set_mcp_header_helper(text, auth.helper)
    if edited is None:
        rep.warn(f"No [mcp_servers.tubematic] in {path} -- the MCP server will refuse this agent "
                 f"(401). Re-run: python onboard.py --install-agent {adapter.name}")
        return
    try:
        tomllib.loads(edited)
    except tomllib.TOMLDecodeError as e:
        rep.warn(f"Not editing {path}: the result would not parse ({e}). Add "
                 f"http_headers_helper = {json.dumps(auth.helper)} under "
                 "[mcp_servers.tubematic] by hand.")
        return
    ex.write_file(path, edited)
    rep.ok(f"MCP header helper set → {path}")


def _install_remotion_skills(cwd: Path, agent_flag: str, *, global_scope: bool = False,
                              ex: Executor = None, rep: Reporter = None) -> bool:
    """Install remotion-dev/skills via the `skills` npm CLI. Requires
    Node >= 22.20.0 (see check_prerequisites). Returns True on success —
    callers should not treat False as fatal (warn-only, same as the
    agent-binary/Node prerequisite checks), but check_installation()
    re-checks the result on disk so a stale failure can't pass as success."""
    ex = ex or _live_ex()
    rep = rep or NullReporter()

    npx_bin = shutil.which("npx")
    if not npx_bin:
        rep.warn("npx not found — remotion-dev/skills skipped. The scene-writing skill "
                 "invokes remotion-best-practices first, so install Node.js >= 22.20 (npx "
                 "comes with it) and re-run --install-agent. Rendering is unaffected.")
        return False
    cmd = ["npx", "--yes", "skills@latest", "add", "remotion-dev/skills", "--all"]
    if global_scope:
        cmd.append("-g")
    cmd += ["-a", agent_flag, "-y"]
    r = ex.run(cmd, cwd=cwd)
    if r.returncode == 0:
        rep.ok("remotion-dev/skills installed")
        return True
    rep.warn(f"remotion-dev/skills install FAILED (exit {r.returncode}) — "
              f"the remotion-best-practices skill will be missing until this is fixed.")
    stderr_tail = [ln for ln in (r.stderr or "").strip().splitlines() if ln.strip()][-5:]
    for line in stderr_tail:
        rep.warn(f"    {line}")
    rep.warn(f"Run manually to retry: {' '.join(cmd)}")
    return False


def describe_existing_workspace(workspace: Path, rep: Reporter, adapter=None) -> None:
    """What a wipe would delete. `adapter` decides which directories to look
    in, so a Codex workspace is not described in Claude's terms; it defaults to
    Claude's layout for the pre-adapter callers."""
    if not workspace.exists():
        return
    # The settings files are Claude's own; an agent that needs no allowlist
    # never has them, so do not go looking for them on its behalf.
    has_settings = adapter is None or adapter.NEEDS_ALLOWLIST
    settings_local = workspace / ".claude" / "settings.local.json"
    settings_json = workspace / ".claude" / "settings.json"
    skills_dir = adapter.project_skills_dir(workspace) if adapter \
        else workspace / ".claude" / "skills"
    cmds_dir = adapter.project_commands_dir(workspace) if adapter \
        else workspace / ".claude" / "commands"
    skills_count = len(list(skills_dir.iterdir())) if skills_dir and skills_dir.is_dir() else 0
    cmds_count = len(list(cmds_dir.glob("*.md"))) if cmds_dir and cmds_dir.is_dir() else 0

    rep.warn(f"Agent workspace already exists: {workspace}")
    if has_settings and settings_local.exists():
        rep.warn("  .claude/settings.local.json present (may contain stale stdio MCP registration)")
    if has_settings and settings_json.exists():
        rep.info("  .claude/settings.json present")
    rep.info(f"  Skills: {skills_count}   Commands: {cmds_count}")


# ── Step 8: Cron jobs ─────────────────────────────────────────────────────────

def apply_cron(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    v = cfg.values
    poll_mins = v.get("POLL_INTERVAL_MINS", "30")

    python_bin = sys.executable
    poll_py = str(REPO_ROOT / "scripts" / "poll.py")
    cron_log = str(POLL_LOG_DIR / "cron.log")

    # The line names no agent (TMDEV-90). poll.py resolves which agent runs —
    # its binary, workspace and model — per video over HTTP, so installing,
    # re-installing or archiving an agent never touches cron, and until one is
    # installed every tick logs "No agent installed" and exits. The one input
    # poll.py cannot get over HTTP is where to log (logging starts first),
    # which is why POLL_LOG_DIR is a fixed path rather than an argument. It has
    # to exist before the first tick: the shell redirect below fails, and the
    # tick with it, if the directory is missing.
    ex.mkdir(POLL_LOG_DIR)
    poll_line = f"*/{poll_mins} * * * * {python_bin} {poll_py} >> {cron_log} 2>&1"

    r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)  # read-only
    existing = r.stdout.splitlines() if r.returncode == 0 else []
    filtered = [l for l in existing if "poll.py" not in l and "# Tubematic" not in l]
    new_lines = filtered + ["", "# Tubematic — managed by onboard.py — do not edit manually",
                             poll_line]

    r2 = ex.crontab_write("\n".join(new_lines) + "\n")
    if r2.returncode != 0:
        rep.warn("crontab write failed — add entries manually (see docs/user-guide/02-installing.md → Manual cron setup)")
        return
    rep.ok("Cron entry written")
    rep.info(f"Poll (advances pipeline + runs research when due): every {poll_mins} min → {cron_log}")

    # Persist the interval for the *next* run's pre-fill. Before TMDEV-73 it was
    # prompted but never stored anywhere, so the question always re-defaulted to
    # 30 no matter what the user had chosen.
    # Genuinely host-side — cron owns it, and a dashboard edit cannot change
    # it — so it is stored for visibility only, outside SETTINGS_SPEC.
    if DB_PATH.exists():
        try:
            _upsert_settings(ex, {"poll_interval_mins": str(poll_mins)}, "record poll interval")
        except Exception as e:
            rep.warn(f"Could not record poll interval: {e}")


# ── Step 10/11: Container builds (LAST) ───────────────────────────────────────

# Compose project name (docker-compose.yml's `name:`) → volume → its device
# subdirectory under DATA_ROOT. Keep in sync with docker-compose.yml.
_VOLUME_DEVICES = {
    "tubematic_output-videos":   "output_videos",
    "tubematic_jobs-data":       "jobs",
    "tubematic_db-data":         "data",
    "tubematic_scenes-generated": "scenes/generated",
    "tubematic_logs-data":        "logs",
    "tubematic_backups-data":     "backups",
}


def _stale_volumes() -> list:
    """(name, current device, expected device) for every volume whose bind
    device no longer matches DATA_ROOT. Read-only — split out so a caller can
    learn that reconciling will run `docker compose down` before it does
    (onboard/stack.py gates on it)."""
    from onboard.config import DATA_ROOT
    stale = []
    for name, subdir in _VOLUME_DEVICES.items():
        r = subprocess.run(  # read-only probe, deliberately outside the executor
            ["docker", "volume", "inspect", name, "--format", "{{.Options.device}}"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            continue  # no such volume — `up` will create it correctly
        current = r.stdout.strip()
        expected = str(DATA_ROOT / subdir)
        if current and current != expected:
            stale.append((name, current, expected))
    return stale


def _reconcile_volume_devices(ex: Executor, rep: Reporter) -> None:
    """Recreate named volumes whose bind device no longer matches compose.

    Docker fixes a named volume's driver_opts when it is created; editing
    docker-compose.yml afterwards does not move an existing one. Compose
    notices and *prompts* — "exists but doesn't match configuration in compose
    file. Recreate (data will be lost)?" — and onboarding runs it
    non-interactively, so the prompt defaults to no and the containers silently
    keep mounting the old path. On an upgrade where the data has already been
    moved to ~/.tubematic-data (TMDEV-76), that means the stack comes up
    against the old, now-empty tree and dockerd recreates it as root.

    Removing the volume is safe and does NOT lose data: these are `o=bind`
    volumes, so the content lives at the device path and Docker only drops its
    own record. Verified directly — a marker file at the old device survived
    `docker volume rm`, and the next `up` bound the new device.
    """
    from onboard.config import DATA_ROOT
    stale = _stale_volumes()
    if not stale:
        return

    rep.warn(f"{len(stale)} Docker volume(s) still point at the previous data location.")
    for name, current, _ in stale:
        rep.info(f"  {name}: {current}")
    rep.info("Recreating them. The files at those paths are NOT deleted — these are bind "
              "volumes, so only Docker's record of them is dropped.")

    # A volume in use cannot be removed, and the containers may still be up
    # from a previous install.
    ex.run([*_compose(), "down"], cwd=REPO_ROOT)
    for name, _, _ in stale:
        r = ex.run(["docker", "volume", "rm", name], cwd=REPO_ROOT)
        if r.returncode != 0:
            rep.fail(f"Could not remove stale volume {name}.",
                      hint=f"Stop anything using it, then: docker volume rm {name}")
            return
    rep.ok(f"Recreated {len(stale)} volume(s) against {DATA_ROOT}")


def _await_health(container: str, url: str, rep: Reporter) -> bool:
    """Block until `container` reports healthy. Returns False on failure.

    Shared by the API and MCP waits (TMDEV-87) so the two cannot drift in
    timeout or in what they report. Read-only `docker inspect`, deliberately
    outside the executor — the same reason _reconcile_volume_devices probes
    directly.
    """
    status = ""
    with rep.spinner(f"Waiting for {container} health check…"):
        for _ in range(12):
            r = subprocess.run(["docker", "inspect", "--format", "{{.State.Health.Status}}", container],
                                capture_output=True, text=True)
            status = r.stdout.strip()
            if status in ("healthy", "unhealthy"):
                break
            time.sleep(5)

    if status == "healthy":
        rep.ok(f"{container} healthy at {url}")
        return True
    if status == "unhealthy":
        rep.fail(f"{container} unhealthy", f"Run: docker compose logs {container}")
        return False

    rep.warn(f"{container} health check timed out — it may still be starting. "
             f"Check: docker compose ps")
    return False


def _pull_failure_hint(r) -> str:
    """What to tell someone whose `docker compose pull` failed.

    The release images are public, so no login is involved: a failed pull is
    this machine not reaching ghcr.io, or a version with no published images,
    and docker's own message says which. It is shown rather than a pointer to
    `docker compose logs`, which prints nothing here -- a pull that fails
    creates no container.
    """
    tail = (r.stderr or "").strip()[-500:]
    advice = "Check that this machine can reach ghcr.io and that this release's images exist."
    return f"{tail}\n{advice}" if tail else advice


def apply_renderer(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    _reconcile_volume_devices(ex, rep)
    mode = _install_mode(cfg)

    if mode == "release":
        with rep.spinner("Pulling tubematic-api image…"):
            r = ex.run([*_compose(), "pull", "tubematic-api"], cwd=REPO_ROOT)
        if r.returncode != 0:
            rep.fail("docker compose pull failed", _pull_failure_hint(r))
            return
        rep.ok("Image pulled")
    else:
        with rep.spinner("Building tubematic-api image…"):
            r = ex.run([*_compose(), "build", "tubematic-api"], cwd=REPO_ROOT)
        if r.returncode != 0:
            rep.fail("docker compose build failed", "Run: docker compose logs tubematic-api")
            return
        rep.ok("Image built")

    ex.ensure_secrets()  # Compose refuses to start a service whose token file is missing
    rep.info("Starting tubematic-api, tubematic-mcp and tubematic-renderer containers…")
    r = ex.run([*_compose(), "up", "-d",
                "tubematic-api", "tubematic-mcp", "tubematic-renderer"], cwd=REPO_ROOT)
    if r.returncode != 0:
        rep.fail("docker compose up failed")
        return

    if ex.dry_run:
        rep.info("[dry-run] would wait for the health checks")
        return

    # Flask and MCP are separate containers with separate healthchecks since
    # TMDEV-87, so they are waited on and reported separately — a healthy Flask
    # no longer implies a live MCP server, which is the whole point of the
    # split. MCP `depends_on` the API, so checking them in this order means the
    # second wait usually returns immediately.
    if not _await_health("tubematic-api", "http://localhost:4000", rep):
        return
    if not _await_health("tubematic-mcp", "http://localhost:4100/mcp", rep):
        return

    r_worker = subprocess.run(["docker", "inspect", "--format", "{{.State.Status}}", "tubematic-renderer"],
                               capture_output=True, text=True)
    if r_worker.stdout.strip() == "running":
        rep.ok("tubematic-renderer (render worker) running")
    else:
        rep.warn("tubematic-renderer container is not running. Check: docker compose logs tubematic-renderer")


def apply_dashboard(cfg: OnboardConfig, ex: Executor, rep: Reporter) -> None:
    mode = _install_mode(cfg)

    if mode == "release":
        with rep.spinner("Pulling tubematic-dashboard image…"):
            r = ex.run([*_compose(), "pull", "tubematic-dashboard"], cwd=REPO_ROOT)
        if r.returncode != 0:
            rep.fail("docker compose pull failed", _pull_failure_hint(r))
            return
        rep.ok("Image pulled")
    else:
        with rep.spinner("Building tubematic-dashboard image…"):
            r = ex.run([*_compose(), "build", "tubematic-dashboard"], cwd=REPO_ROOT)
        if r.returncode != 0:
            rep.fail("docker compose build failed", "Run: docker compose logs tubematic-dashboard")
            return
        rep.ok("Image built")

    rep.info("Starting tubematic-dashboard container…")
    ex.ensure_secrets()  # Compose refuses to start a service whose token file is missing
    r = ex.run([*_compose(), "up", "-d", "tubematic-dashboard"], cwd=REPO_ROOT)
    if r.returncode != 0:
        rep.fail("docker compose up failed")
        return

    if ex.dry_run:
        rep.info("[dry-run] would confirm the container is running")
        return
    rep.ok("tubematic-dashboard running at http://localhost:3000")


# ── Dispatch ─────────────────────────────────────────────────────────────────

ACTIONS = {
    "prerequisites":     apply_prerequisites,
    "python_deps":       apply_python_deps,
    "directories":       apply_directories,
    "database":          apply_database,
    "auth":              apply_auth,
    "install_config":    apply_install_config,
    "pipeline_settings": apply_pipeline_settings,
    "cron":              apply_cron,
    "renderer":          apply_renderer,
    "dashboard":         apply_dashboard,
}
