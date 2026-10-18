#!/usr/bin/env python3
"""Tubematic pipeline poller.

Pure Python — zero LLM cost on empty polls.
Checks pipeline state via the Flask API (:4000), then invokes the agent each
piece of work is assigned to, only when actionable work exists. No direct DB
access — the installed agents, like everything else, come over HTTP.

Called on a schedule by OS cron (written by onboard.py). The tick that takes
the lock becomes the supervisor: it keeps looping — dispatching one agent
session per video, up to max_concurrent_agent_sessions at once, plus a research
lane and a script-profile lane of one each — until nothing is running and
nothing is left to start (TMDEV-129). A tick that finds the lock held exits;
cron is a watchdog that restarts the supervisor, not the thing that paces it.

Usage:
  python poll.py              # supervise until idle
  python poll.py --dry-run    # print what one pass would start; invoke nothing

Research runs at most once per supervisor, as long as research_pending_cap and
max_research_runs_per_day (a rolling 24h count, both settings-table keys) allow.

Logs:
  Written to ~/.tubematic-agent/logs/poll.log with daily rotation (14-day retention).
  Console output is shown only when running in a TTY or with --dry-run.
"""
import concurrent.futures
import contextvars
import fcntl
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
from typing import NamedTuple

SCRIPTS_DIR = Path(__file__).parent
sys.path.insert(0, str(SCRIPTS_DIR))
# The repo root, for the shared tubematic_core package. Inside the containers
# that comes from PYTHONPATH; poll.py runs on the host, from the checkout.
sys.path.insert(0, str(SCRIPTS_DIR.parent))

from config import (  # noqa: E402
    DATA_ROOT, RENDERER_URL, POLL_LOG_DIR, LOCAL_TZ_LABEL,
)
from tubematic_core import logging as tlog  # noqa: E402
from agent_adapters import ADAPTERS, clip  # noqa: E402

# poll.py's own log directory. Fixed rather than read off argv: the cron line
# names no agent (TMDEV-90) — which agent runs, and from which binary and
# workspace, is resolved per video over HTTP — but logging starts before the
# first HTTP call. Everything else comes over HTTP: this module has no DB
# access by design.
LOG_DIR = POLL_LOG_DIR

# Flags a crontab written before TMDEV-90 still passes. Accepted and ignored
# with a warning — failing on them would stop the pipeline on an upgrade that
# has not re-run the cron step yet.
_LEGACY_FLAGS = ("--agent-run-path", "--agent-binary")


def _legacy_flags(argv: list) -> list:
    return [flag for flag in _LEGACY_FLAGS if flag in argv]

# Beside the logs rather than in /tmp, so every Tubematic file lives at a known
# location — and because pollers that share a home directory (Kasm sessions on
# one persistent profile) must share one lock, which a per-container /tmp is not.
LOCKFILE           = POLL_LOG_DIR.parent / "poll.lock"

# ── Supervisor state files (TMDEV-129), all beside the lock ─────────────────
# The supervisor touches HEARTBEAT on every pass. A tick that finds the lock
# held reads its age: flock is released by the kernel when its holder dies, so
# a held lock always means a live supervisor, and a stale heartbeat means a
# live but hung one. That is logged, never acted on — killing it could kill a
# session in the middle of a paid call.
HEARTBEAT            = POLL_LOG_DIR.parent / "poll.heartbeat"
HEARTBEAT_STALE_SECS = 300
# Every running agent process, so a supervisor that dies (OOM, kill -9, a
# reboot of the container but not the profile) leaves a record the next one
# can adopt instead of double-dispatching the same video.
REGISTRY             = POLL_LOG_DIR.parent / "poll-sessions.json"
# Agent output goes to files here, not pipes: an orphan writing into a pipe
# whose reader died would take SIGPIPE mid-work, and a file is still readable
# by whichever supervisor finishes its bookkeeping.
SESSIONS_DIR         = POLL_LOG_DIR.parent / "sessions"

# How long a pass waits for a session to finish before looking again.
LOOP_WAIT_SECS       = 60
# SIGTERM, then this long, then SIGKILL, when a session outlives its timeout.
KILL_GRACE_SECS      = 10
# Fallbacks for the two settings, used only if /settings cannot be read.
# Keep in sync with renderer/api/pipeline.py SETTINGS_SPEC.
DEFAULT_MAX_SESSIONS    = 3
MAX_SESSIONS_CEILING    = 10     # pipeline.MAX_CONCURRENT_AGENT_SESSIONS
DEFAULT_SESSION_TIMEOUT = 5400

# The statuses a scene-work claim can be held in, and how long a dead session's
# claim outlives it. The claim is keyed to the MCP session, so a new session
# dispatched onto the same video inside that window is refused with
# scene_work_claimed and ends having done nothing. The TTL was sized for a
# 30-minute tick gap that the looping supervisor removed, so the supervisor now
# waits it out itself. Keep in sync: mcp/server.py SCENE_CLAIM_TTL_SECS and
# _CLAIM_STATUSES.
CLAIM_STATUSES          = frozenset({"VOICE_READY", "REVISION_REQUESTED"})
CLAIM_COOLDOWN_SECS     = 900

# One stage per session: where a session starts, and the statuses at which it
# must stop. A revision continues through VOICE_READY, because the scene-work
# claim spans REVISION_REQUESTED → VOICE_READY → RENDER_QUEUED and is keyed to
# the session: splitting that window across two sessions would have the
# second refused by the first's claim. Keep the keys in sync with
# renderer/api/pipeline.py WORKABLE_STATUSES.
STAGES = {
    "TOPIC_APPROVED":     ("scripting",  ("SCRIPT_READY",)),
    "VOICING":            ("voicing",    ("VOICE_READY",)),
    "VOICE_READY":        ("scene work", ("RENDER_QUEUED",)),
    "REVISION_REQUESTED": ("a revision", ("TOPIC_PROPOSED", "SCRIPT_READY", "VOICING",
                                          "RENDER_QUEUED")),
}
# End statuses that mean a session ran past its stage — its cost is then
# recorded under the wrong stage. Only VOICING has a status-only tell: a
# revision's route (topic, script, pronunciation, animation) is not visible in
# its end status, and the other stages end at a human checkpoint or at the
# render queue, which the render worker moves on from by itself.
OVERRUN = {
    "VOICING": frozenset({"RENDER_QUEUED", "RENDERING", "VIDEO_READY"}),
}

# Retention for poll.log, the plain-text log in the agent workspace. This is a
# *different* store from the shared JSONL one under DATA_ROOT/logs, and the
# numeric match with the log_retention_days setting's default is a coincidence,
# not a shared policy — poll.log predates it, onboarding creates and checks its
# directory, and nothing in tubematic_core manages it.
LOG_RETENTION_DAYS = 14

# The shared structured-log directory, the same one the containers mount at
# /logs. poll.py writes poll.*.jsonl here so a cron tick shows up in the
# dashboard's Logs page alongside the three services.
JSONL_LOG_DIR = DATA_ROOT / "logs"

log = logging.getLogger("poll")


# ── Logging setup ─────────────────────────────────────────────────────────────

def _setup_logging(dry_run: bool = False) -> None:
    """Configure file-based rotating logger + optional console handler.

    File handler: always written to LOG_DIR/poll.log, daily rotation, host-local
    timestamps (with UTC offset), 14-day retention.
    Console handler: only when running interactively (TTY) or with --dry-run.
    Cron invocations have no TTY — file-only.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    # [%(session)s] names the session a line belongs to — several run at
    # once, and their lines interleave in one file (TMDEV-129).
    fmt = logging.Formatter(
        "%(asctime)s %(levelname)-7s [%(session)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )
    # Default converter is time.localtime — matches the host's timezone.

    file_handler = TimedRotatingFileHandler(
        LOG_DIR / "poll.log",
        when="midnight",
        backupCount=LOG_RETENTION_DAYS,
    )
    file_handler.setFormatter(fmt)
    file_handler.setLevel(logging.DEBUG)
    file_handler.addFilter(_SessionContext())

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    root.addHandler(file_handler)

    if dry_run or sys.stderr.isatty():
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(fmt)
        console.setLevel(logging.INFO)
        console.addFilter(_SessionContext())
        root.addHandler(console)

    # A third sink, added alongside — poll.log is unchanged, and is still what
    # the existing cron-tick checks read.
    #
    # Retention comes over HTTP rather than out of the settings table: this
    # module has no database access by design (see scripts/config.py), and
    # reaching for sqlite3 here to read one integer would spend that invariant
    # cheaply. An unreachable API falls back to the default, which is the same
    # thing that happens on a fresh install before anything is seeded.
    handler = tlog.setup_json_logging(
        "poll", JSONL_LOG_DIR,
        retention_days=_json_log_retention_days(),
        secrets=(),
    )
    # setup_json_logging returns None quietly by design -- logging must never
    # take a service down. Quiet is right for it and wrong here: poll.py is the
    # only writer that runs as the host user, so a root-owned logs/ drops every
    # poll entry from the dashboard with no other trace anywhere (TMDEV-94).
    if handler is not None:
        handler.addFilter(_SessionContext())
    if handler is None:
        log.warning(
            "Cannot write %s -- poll entries will not appear on the dashboard's "
            "Logs page. Fix with: sudo chown \"$USER:$USER\" %s "
            "(restarting the stack also repairs it).",
            JSONL_LOG_DIR, JSONL_LOG_DIR,
        )


def _json_log_retention_days() -> int:
    """log_retention_days over HTTP, falling back to the spec default."""
    import urllib.request
    import json as _json
    try:
        with urllib.request.urlopen(f"{RENDERER_URL}/settings", timeout=5) as r:
            value = int(_json.loads(r.read())["log_retention_days"])
        return value if 1 <= value <= 365 else LOG_RETENTION_DAYS
    except Exception:
        return LOG_RETENTION_DAYS


# ── Helpers ──────────────────────────────────────────────────────────────────

def _now_iso() -> str:
    """Host-local timestamp with UTC offset and zone label, e.g.
    '2026-07-25T21:07:53-0400 (EDT (UTC-04:00))'."""
    ts = datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")
    return f"{ts} ({LOCAL_TZ_LABEL})"


def _fetch_pipeline_status() -> dict:
    """GET /pipeline/status from the Flask API. Returns {} on failure."""
    import urllib.request
    import json as _json
    try:
        with urllib.request.urlopen(f"{RENDERER_URL}/pipeline/status", timeout=5) as r:
            return _json.loads(r.read())
    except Exception as e:
        log.error("Could not reach Flask API: %s", e)
        return {}


def resolve_agent_binary(agent: dict) -> str | None:
    # Re-resolved through PATH rather than exec'd as stored: the value comes
    # from the agents table over HTTP, and running an arbitrary stored path
    # unchecked would be a new code-execution surface (see TMDEV-31).
    # shutil.which accepts an absolute path and verifies it is executable, so
    # this still works for the resolved form onboarding writes.
    binary = shutil.which(agent.get("binary") or "")
    if not binary:
        log.error("Agent %r: binary %r not found in PATH. Re-run: python onboard.py "
                  "--install-agent %s", agent.get("id"), agent.get("binary"), agent.get("id"))
    return binary


def resolve_agent_cwd(agent: dict) -> Path:
    """Return the agent's own workspace, creating it if needed.

    An agent always runs from its workspace — never the repo root. Running
    from the repo would give it unnecessary access to source, the SQLite DB,
    and mounted video volumes.
    """
    workspace = Path(agent["run_path"]).expanduser()
    if not workspace.exists():
        log.info("Creating agent workspace: %s", workspace)
        workspace.mkdir(parents=True, exist_ok=True)
    return workspace


def _fetch_agents() -> list | None:
    """GET /agents, archived rows included.

    None when the request fails — deliberately distinct from [] (nothing
    installed): the first is a transient outage, the second a state the user
    has to act on, and they are logged differently.
    """
    import urllib.request
    import json as _json
    try:
        with urllib.request.urlopen(f"{RENDERER_URL}/agents", timeout=10) as r:
            agents = _json.loads(r.read())
        return agents if isinstance(agents, list) else None
    except Exception as e:
        log.error("Could not fetch installed agents: %s", e)
        return None


def _default_agent(agents: list) -> dict | None:
    """The live default agent, else the oldest live one, else None."""
    live = [a for a in agents if not a.get("archived_at")]
    return next((a for a in live if a.get("is_default")), None) or (live[0] if live else None)


def _default_model(agent: dict) -> str:
    """An agent's default model: the first of its install-validated models."""
    models = agent.get("models") or []
    return models[0] if models else ""


def _default_effort(agent: dict) -> str:
    """An agent's default effort level, the sibling of _default_model.

    Blank when the row predates the column, which means "pass no --effort flag"
    — the CLI's own default, a working run either way.
    """
    return (agent.get("effort") or "").strip()


def _video_agent(video: dict, by_id: dict, default: dict, quiet: bool = False) -> dict | None:
    """The agent a workable video runs under, or None to skip it this tick.

    The poller never moves a video to another agent: one whose agent is
    uninstalled (archived_at set) or gone is skipped loudly — never rerouted,
    which would switch prompt tuning and style mid-task. Only a human changes a
    video's agent, and only at a checkpoint (TMDEV-110); a video stranded
    between checkpoints resumes when its agent is re-installed.
    A video with no agent_id predates per-video agents and belongs to the default.
    `quiet` suppresses the error for a video already reported by this
    supervisor, which would otherwise repeat it on every pass.
    """
    agent_id = video.get("agent_id")
    if not agent_id:
        return default
    agent = by_id.get(agent_id)
    if agent is None or agent.get("archived_at"):
        state = "not installed" if agent is None else "uninstalled"
        if quiet:
            return None
        log.error("Video %s is assigned to agent %r, which is %s — skipped. "
                  "Re-install it to resume: python onboard.py --install-agent %s",
                  video.get("id"), agent_id, state, agent_id)
        return None
    return agent


def _usable_model(model: str) -> str:
    """The model to actually pass on argv, or "" to pass no --model at all.

    A value that would corrupt the invocation (embedded spaces, or a leading
    dash the CLI would read as another flag) is dropped rather than passed:
    with no --model flag the agent CLI falls back to its own default, which is
    a working run instead of a broken one. The API rejects both shapes at write
    time, so this is the backstop for a row that got in another way.

    Deliberately not a catalog check — a misspelled but well-formed model name
    is not detectable before the run. It is NOT a non-zero exit either: the
    Claude CLI exits 0 on an unknown model. invoke_agent catches it afterwards
    from the agent's output (ClaudeAdapter.model_rejected) and re-runs once
    with the CLI default.
    """
    model = (model or "").strip()
    if not model:
        return ""
    if " " in model or model.startswith("-"):
        log.warning("Ignoring unusable agent model %r — invoking with the CLI default instead",
                    model)
        return ""
    return model


def _usable_effort(adapter, effort: str) -> str:
    """The effort to actually pass on argv, or "" to pass no --effort at all.

    Unlike _usable_model this IS a membership check, and can be: the levels are
    a closed set the CLI documents in its own --help, so a wrong value is
    detectable before the run rather than only from the output afterwards.
    Dropping it means no --effort flag, i.e. the CLI's own default effort —
    a working run instead of a wasted one, the same bargain _usable_model makes.

    The API rejects a bad value at write time, so this is the backstop for a
    row that got in another way, and for an agent installed against a CLI whose
    level names have since changed.
    """
    effort = (effort or "").strip()
    if not effort:
        return ""
    if effort not in adapter.EFFORTS:
        log.warning("Ignoring unusable agent effort %r (known levels: %s) — invoking with the "
                    "CLI default instead", effort, ", ".join(adapter.EFFORTS))
        return ""
    return effort


class _Verdict(NamedTuple):
    """What one finished agent run says about the flags it was given."""
    model_rejected: bool = False
    effort_rejected: bool = False


# ── Sessions (TMDEV-129) ─────────────────────────────────────────────────────

class _Session:
    """One agent session the supervisor started or adopted.

    A session is one invoke_agent call: up to three agent processes (the
    effort/model retry chain), all under one deadline. `video_id` is set for
    the pipeline lane only; research and script profiles have no video to
    score.
    """

    def __init__(self, lane: str, label: str, *, video_id: str = "", start_status: str = "",
                 profile_id: str = "", agent_id: str = "", model: str = "",
                 operation: str = "", attribution=(), deadline: float | None = None):
        self.lane = lane
        self.label = label
        self.video_id = video_id
        self.start_status = start_status
        self.profile_id = profile_id
        self.agent_id = agent_id
        self.model = model
        self.operation = operation
        self.attribution = list(attribution)
        self.deadline = deadline          # wall clock: it is shared across processes
        self.runs = 0                     # agent processes started
        self.returncode: int | None = None
        self.timed_out = False
        # Ties the session's registry entries together: a retry is a second
        # process, and all of them stay registered until the session is scored.
        self.key = uuid.uuid4().hex


# The session the current thread is working for. Each session runs in its own
# empty Context, so this never leaks into the next session on a reused thread.
_current_session: contextvars.ContextVar = contextvars.ContextVar("poll_session", default=None)


class _SessionContext(logging.Filter):
    """Label every log line with the session it came from.

    `session` feeds poll.log's [..] column; video_id / profile_id are the
    JSONL sink's context fields, so the dashboard's Logs page can filter a
    video's lines without any change to the shared formatter.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        session = _current_session.get()
        record.session = session.label if session else "supervisor"
        if session and session.video_id and not getattr(record, "video_id", None):
            record.video_id = session.video_id
        if session and session.profile_id and not getattr(record, "profile_id", None):
            record.profile_id = session.profile_id
        return True


class _Result(NamedTuple):
    """One finished agent process, in the shape subprocess.run used to give."""
    returncode: int
    stdout: str
    stderr: str
    timed_out: bool = False
    run_id: str = ""        # the process's registry entry, while its bookkeeping is owed


def _proc_start(pid: int) -> str | None:
    """A live process's start time from /proc, or None if it is gone or a zombie.

    The pair (pid, start time) names one process for good; a pid alone can be
    reused by an unrelated process after the original exits.
    """
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    # The command name is in parentheses and may itself contain spaces or
    # parentheses, so split after the LAST ")". Field 3 (state) is then [0]
    # and field 22 (starttime) is [19].
    fields = stat.rsplit(")", 1)[-1].split()
    if len(fields) < 20 or fields[0] == "Z":
        return None
    return fields[19]


_registry_lock = threading.Lock()


def _registry_read() -> list:
    try:
        entries = json.loads(REGISTRY.read_text())
    except (OSError, ValueError):
        return []
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _registry_write(entries: list) -> None:
    # tmp + rename, so a supervisor killed mid-write leaves the old file whole.
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    tmp = REGISTRY.with_name(REGISTRY.name + ".tmp")
    tmp.write_text(json.dumps(entries))
    os.replace(tmp, REGISTRY)


def _registry_add(pid: int, session: "_Session", out_path: Path, err_path: Path) -> str:
    """Register one agent process; return its run id.

    The run id doubles as the usage record's session_id, which the ledger is
    idempotent on — so a supervisor that re-reports a run another one already
    reported records nothing twice.
    """
    run_id = uuid.uuid4().hex
    entry = {"pid": pid, "proc_start": _proc_start(pid), "run_id": run_id,
             "session_key": session.key, "usage_done": False, "lane": session.lane,
             "label": session.label, "video_id": session.video_id,
             "start_status": session.start_status, "profile_id": session.profile_id,
             "agent_id": session.agent_id, "model": session.model,
             "operation": session.operation, "attribution": session.attribution,
             "deadline": session.deadline, "stdout": str(out_path), "stderr": str(err_path)}
    with _registry_lock:
        _registry_write(_registry_read() + [entry])
    return run_id


def _registry_run_done(run_id: str) -> None:
    """A run's usage is recorded: drop its output files, keep its entry.

    The entry stays until the whole session is scored, so a supervisor that
    dies between the two still leaves the outcome to its successor.
    """
    with _registry_lock:
        entries = _registry_read()
        for e in entries:
            if e.get("run_id") == run_id:
                e["usage_done"] = True
                for key in ("stdout", "stderr"):
                    Path(e.get(key) or "/nonexistent").unlink(missing_ok=True)
        _registry_write(entries)


def _registry_remove_session(session_key: str) -> None:
    with _registry_lock:
        _registry_write([e for e in _registry_read() if e.get("session_key") != session_key])


def _registry_remove_runs(entries: list) -> None:
    """Remove exactly these entries — by run id, else by pid."""
    ids = {(e.get("run_id"), e.get("pid")) for e in entries}
    with _registry_lock:
        _registry_write([e for e in _registry_read() if (e.get("run_id"), e.get("pid")) not in ids])


def _read(path: Path) -> str:
    try:
        return path.read_text(errors="replace")
    except OSError:
        return ""


def _group_alive(pgid: int) -> bool:
    """Whether any process is still in the group — signal 0 checks without sending."""
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _entry_group_alive(entry: dict) -> bool:
    """Whether a registered process's group still has members — safely.

    The kernel does not reuse a pid while a process group with that id still
    has members. So a live process now holding the pid under a different start
    time means our group is gone and the pid was reused: signalling that group
    would hit an unrelated process tree. With no process at the pid, a group
    that still answers is ours — a leader that exited, and children that did
    not.
    """
    pid = entry["pid"]
    start = _proc_start(pid)
    if start is not None and start != entry.get("proc_start"):
        return False
    return _group_alive(pid)


def _stop_group(proc) -> int:
    """SIGTERM the session's process group, then SIGKILL whatever is left of it.

    The grace is measured against the whole group, never the leader alone: an
    agent that exits promptly on SIGTERM can leave a child that ignores it, and
    that child could go on spending — and changing the video — after the
    session has been scored and a replacement dispatched.
    """
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    returncode = None
    deadline = time.monotonic() + KILL_GRACE_SECS
    while time.monotonic() < deadline:
        if returncode is None:
            returncode = proc.poll()
        if returncode is not None and not _group_alive(proc.pid):
            return returncode
        time.sleep(0.2)
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    return proc.wait() if returncode is None else returncode


def _execute(cmd: list, cwd: Path) -> _Result:
    """Run one agent process to completion, or until its session's deadline.

    start_new_session puts the agent and anything it spawns in their own
    process group, so a timeout can killpg the lot. PR_SET_PDEATHSIG is not
    used: it fires when the *thread* that forked exits, not the process, and
    these processes are started from pool threads. A supervisor's death is
    covered by the registry instead.
    """
    session = _current_session.get()
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    stem = SESSIONS_DIR / uuid.uuid4().hex
    out_path, err_path = Path(f"{stem}.out"), Path(f"{stem}.err")
    # stdin is closed, never inherited: `codex exec` reads piped stdin and
    # appends it to the prompt, so an inherited stdin can block an unattended
    # run indefinitely. Claude ignores stdin, so this is unconditional.
    try:
        with open(out_path, "wb") as out, open(err_path, "wb") as err:
            proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.DEVNULL, stdout=out,
                                    stderr=err, start_new_session=True)
    except OSError:
        out_path.unlink(missing_ok=True)
        err_path.unlink(missing_ok=True)
        raise
    run_id = ""
    if session is not None:
        session.runs += 1
        run_id = _registry_add(proc.pid, session, out_path, err_path)
    timed_out = False
    try:
        timeout = None
        if session is not None and session.deadline is not None:
            timeout = max(0.0, session.deadline - time.time())
        try:
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            log.error("Session passed agent_session_timeout_secs — stopping its process group "
                      "(pid %d)", proc.pid)
            returncode = _stop_group(proc)
    except BaseException:
        if run_id:
            _registry_run_done(run_id)
        raise
    result = _Result(returncode, _read(out_path), _read(err_path), timed_out, run_id)
    # Without a session there is no registry entry to keep the files for.
    if not run_id:
        out_path.unlink(missing_ok=True)
        err_path.unlink(missing_ok=True)
    return result


def invoke_agent(prompt: str, agent: dict, dry_run: bool = False, model: str = "",
                 effort: str = "", operation: str = "agent_pipeline",
                 attribution=()) -> None:
    """Run one session of `agent` (a GET /agents row) on `prompt`.

    At most THREE subprocess runs, ever: the real one, plus one retry per
    dropped flag, and each flag is dropped at most once along any path.
    Effort is dropped before model, because an effort rejection means the CLI
    refused to start at all, so nothing else about that run can be believed.
    Without a cap this shape loops.

    The two orders both terminate in three: effort-then-model, and — for an
    agent whose effort rejection depends on the model — model-then-effort,
    where the CLI's own fallback model turns out not to accept the effort that
    the chosen model did.
    """
    adapter = ADAPTERS.get(agent.get("id"))
    if adapter is None:
        log.error("No adapter for agent %r — supported: %s",
                  agent.get("id"), ", ".join(ADAPTERS))
        return
    binary = resolve_agent_binary(agent)
    if not binary:
        return
    model = _usable_model(model)
    effort = _usable_effort(adapter, effort)
    if dry_run:
        _, redacted_cmd = _argv(adapter, binary, prompt, model, effort)
        log.info("[DRY RUN] Would invoke: %s", " ".join(redacted_cmd))
        log.debug("[PROMPT PREVIEW]\n%s", prompt[:800] + ("..." if len(prompt) > 800 else ""))
        return
    cwd = resolve_agent_cwd(agent)
    log.debug("Prompt:\n%s", prompt)
    # What each run's usage is recorded against (TMDEV-107): the kind of run,
    # and the videos it was for with the status each was at when it started.
    usage = {"operation": operation, "videos": list(attribution)}

    verdict = _run_agent(adapter, binary, prompt, cwd, model, effort, usage)

    # ── Run 2: drop --effort ────────────────────────────────────────────────
    # An older CLI that has never heard of the flag exits non-zero having done
    # nothing at all, so this is a whole tick lost rather than a degraded one.
    if verdict.effort_rejected:
        if not effort:
            log.error("Agent reports an unknown --effort option although none was passed — "
                      "nothing to fall back from")
            return
        log.error("Agent CLI does not accept --effort (was %r) — re-running once with the flag "
                  "omitted, at the CLI's own default effort. Upgrade the CLI, or re-run "
                  "`python onboard.py --install-agent %s` to check it.", effort, agent.get("id"))
        effort = ""
        verdict = _run_agent(adapter, binary, prompt, cwd, model, effort, usage)
        if verdict.effort_rejected:
            log.error("Agent still reports an unknown --effort option with no --effort flag")
            return

    # ── Run 3: drop --model ─────────────────────────────────────────────────
    if not verdict.model_rejected:
        return
    if not model:
        log.error("Agent reported an unrecognized model although none was passed — "
                  "nothing to fall back from")
        return
    # A bad model makes a run that does nothing, every tick, indefinitely —
    # so fall back rather than just report: no --model flag means the CLI's
    # own default, a working run instead of a wasted one. Whatever effort
    # survived above is kept: the two flags fail independently.
    log.error("Agent rejected model %r (unrecognized, or not available to this account) — "
              "re-running once with the CLI default", model)
    verdict = _run_agent(adapter, binary, prompt, cwd, "", effort, usage)
    if verdict.model_rejected:
        log.error("Agent still reports an unrecognized model with no --model flag")
        return
    # ── Run 3: the CLI's own default model may not accept this effort ───────
    # Reachable only in this order, and only for an agent whose effort
    # rejection depends on the model: the effort was fine for the model we
    # asked for, so the block above never fired, and the fallback model is one
    # nobody chose. Leaving it unhandled costs the whole tick, silently.
    # Still at most three runs: arriving here means the effort block was
    # skipped, so each flag is dropped at most once along any path.
    if verdict.effort_rejected and effort:
        log.error("The CLI's own default model does not accept effort %r either — re-running "
                  "once with no effort flag", effort)
        _run_agent(adapter, binary, prompt, cwd, "", "", usage)


def _argv(adapter, binary: str, prompt: str, model: str, effort: str) -> tuple:
    """(argv, argv with the prompt redacted) for one run."""
    cmd = adapter.build_argv(binary, prompt, model, effort)
    return cmd, ["<prompt>" if part == prompt else part for part in cmd]


def _run_agent(adapter, binary: str, prompt: str, cwd: Path, model: str,
               effort: str, usage: dict = None) -> _Verdict:
    """Run one agent session and log it, returning what it says about its flags.

    The model verdict comes from the output, never the exit code: the Claude
    CLI exits 0 on an unknown model, so a returncode check alone logs
    "completed" for a run that did nothing. The effort verdict is the opposite
    shape — a non-zero exit with an unknown-option message on stderr — which is
    why the adapter owns both matchers rather than this function.
    """
    cmd, redacted_cmd = _argv(adapter, binary, prompt, model, effort)
    log.debug("Invoking agent: cwd=%s cmd=%s", cwd, " ".join(redacted_cmd))
    result = _execute(cmd, cwd=cwd)
    session = _current_session.get()
    if session is not None:
        session.returncode = result.returncode
        session.timed_out = session.timed_out or getattr(result, "timed_out", False)
    # The JSON output modes make stdout the whole session, tool results and
    # all, so the log gets the adapter's summary; stderr keeps its tail, which
    # is where a crash's error lands. The verdicts below still read everything.
    if result.stdout and result.stdout.strip():
        log.info("%s", adapter.summarize_output(result.stdout))
    if result.stderr:
        log.warning("Agent stderr:\n%s", clip(result.stderr.strip(), keep="tail"))
    # Every run is recorded, retries included — each was a separately billed
    # session. A run that never started (a rejected flag) reports no usage.
    run_id = getattr(result, "run_id", "")
    if usage is not None:
        _report_usage(adapter, binary, cwd, model, result, usage, session_id=run_id)
    if run_id:
        _registry_run_done(run_id)
    # A killed run says nothing about its flags, and retrying it would only
    # start another process past the session's deadline.
    if getattr(result, "timed_out", False):
        return _Verdict()
    if adapter.effort_rejected(result.stderr or "", result.returncode, result.stdout or ""):
        return _Verdict(effort_rejected=True)
    if adapter.model_rejected(f"{result.stdout or ''}\n{result.stderr or ''}",
                              result.returncode):
        return _Verdict(model_rejected=True)
    if result.returncode != 0:
        log.error("Agent exited with code %d", result.returncode)
    else:
        log.info("Agent completed (exit 0)")
    return _Verdict()


def _report_usage(adapter, binary: str, cwd: Path, model: str, result, usage: dict,
                  session_id: str = "") -> None:
    """POST one run's usage to the Flask API for the ledger. Never raises.

    This module has no database access by design, so usage travels over HTTP
    like the research-run record does. It fails open — bookkeeping must not
    cost a tick — but never silently: if the POST fails, the full payload is
    logged, so the units (the part that cannot be recovered later) survive in
    poll.log and can be re-sent.
    """
    import json as _json
    import urllib.request
    import uuid

    def fetch(session_id: str) -> str:
        # Retried, and every miss logged: observed live, the read can fail
        # right after a run that ended on a provider error, then succeed
        # moments later — and a silent miss leaves only the stream fallback,
        # which can drop the last step's usage.
        argv = adapter.session_usage_argv(binary, session_id)
        for attempt in range(1, 4):
            try:
                r = subprocess.run(argv, cwd=cwd, capture_output=True, text=True,
                                   stdin=subprocess.DEVNULL, timeout=60)
                if r.returncode == 0 and r.stdout.lstrip().startswith("{"):
                    return r.stdout
                why = f"exit {r.returncode}: {(r.stderr or r.stdout).strip()[:200]}"
            except (OSError, subprocess.TimeoutExpired) as e:
                why = str(e)
            log.warning("Reading session %s's usage failed (attempt %d of 3) — %s",
                        session_id, attempt, why)
            if attempt < 3:
                time.sleep(5)
        return ""

    try:
        events = adapter.parse_usage(
            result.stdout or "", model=model,
            fetch=fetch if hasattr(adapter, "session_usage_argv") else None)
    except Exception as e:
        log.warning("Could not read the agent's usage from its output: %s", e)
        return
    if not events:
        return
    payload = _json.dumps({"session_id": session_id or str(uuid.uuid4()), "agent": adapter.name,
                           "operation": usage["operation"], "videos": usage["videos"],
                           "events": events})
    try:
        req = urllib.request.Request(f"{RENDERER_URL}/usage/agent-session", method="POST",
                                     data=payload.encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            recorded = _json.loads(resp.read().decode() or "{}").get("recorded")
        # A 200 is not enough: the API answers 200 even when it could record
        # only some of the events, and those units would otherwise be lost.
        if recorded != len(events):
            raise RuntimeError(f"only {recorded} of {len(events)} event(s) were recorded")
    except Exception as e:
        # Safe to resend as-is: the route is idempotent per session_id and
        # event position, so events that did land are not recorded twice.
        log.warning("Could not record this run's usage (%s). Payload, for re-sending to "
                    "POST /usage/agent-session: %s", e, payload)
        return
    log.info("Recorded usage for %s: %s", usage["operation"], ", ".join(
        f"{ev.get('model') or '?'}" for ev in events))


def _preferences_block(preferences: str, stage: str) -> list[str]:
    """The operator's standing preferences, fenced for one prompt (TMDEV-117).

    Empty text yields no lines at all, so an install that never sets them sends
    exactly the prompt it always did. The text mixes stages, hence the stage
    name and the "only what fits" instruction; and it is free text a human
    wrote, so it is told plainly that it cannot move a human checkpoint.
    """
    text = (preferences or "").strip()
    if not text:
        return []
    return [
        "=== USER PREFERENCES (written by the operator in the Tubematic dashboard) ===",
        "Standing preferences for every video Tubematic produces. They cover several stages",
        f"at once (topic research, scripting, voice, visuals, ...). This run's stage: {stage}.",
        "Apply ONLY the instructions relevant to this stage and ignore the rest.",
        "They never override the pipeline's rules: human checkpoints, tool contracts,",
        "per-run caps and status transitions still apply.",
        "",
        text,
        "=== END USER PREFERENCES ===",
        "",
    ]


def build_pipeline_prompt(video_id: str, status: str, preferences: str = "") -> str:
    """The prompt for one session: one video, one stage (TMDEV-129).

    The scope lives here rather than in the operator skill, so an interactive
    session keeps its multi-video, multi-stage behaviour. Stopping at the
    stage's end is what makes the session's recorded cost belong to one stage,
    and what lets the next stage start in a fresh session straight away.
    """
    stage, stops = STAGES.get(status, ("the next step", ()))
    stop_list = " or ".join(stops) if stops else "a status other than " + status
    lines = [
        f"[TUBEMATIC POLL — {_now_iso()}]",
        "",
        "Invoke the tubematic-operator skill and advance ONE video by ONE stage.",
        "",
        f"This run is scoped to video {video_id}, currently at {status} ({stage}).",
        "Work only on this video. Other videos are advanced by their own sessions, some of",
        "them running at the same time as this one: do not list, read or change any other",
        "video, and do not go looking for more work with list_videos or get_pipeline_status.",
        "Reading install settings from get_pipeline_status is fine when a skill asks for them",
        "(the pronunciation lexicon, the voice roster): that is not looking for work.",
        f"Stop as soon as this video's status is {stop_list}, then end the session:",
        "the next stage runs in a new session.",
    ]
    if status == "REVISION_REQUESTED":
        lines += [
            "A pronunciation revision ends at VOICING: fix the lexicon or the respelling, set",
            "the status to VOICING and end the session. Do NOT call generate_voice here; the",
            "voicing and the scene work each run in a session of their own.",
            "An animation revision passes through VOICE_READY on its way to RENDER_QUEUED.",
            "Do NOT stop at VOICE_READY: keep going until the render is submitted.",
        ]
    lines += [
        "If you cannot move the video forward, add a comment on it saying why, and end the",
        "session.",
        "",
        "Use the tubematic MCP tools to:",
        f"  1. Call get_video(\"{video_id}\") then follow the operator skill's action for its status",
        "  2. Stop at human checkpoints (SCRIPT_READY, VIDEO_READY) and add a comment",
        "",
        "VOICING is not a checkpoint. The video was moved there by an approval of its script",
        "(a human's, or Auto Pilot's on an install that has it on),",
        "so the paid ElevenLabs call and sending the script to ElevenLabs are pre-authorized.",
        "Call generate_voice without asking: no human is present on this run to answer, and",
        "refusing leaves the video stuck in VOICING. The same holds for a",
        "re-voice after a pronunciation fix: the original script approval covers it.",
        "",
        "Do not research new topics during this run.",
        "",
        *_preferences_block(preferences, f"advancing one video ({stage})"),
        "IMPORTANT: Skip the operator skill setup checks (docker/curl health checks).",
        "The poller has already verified the renderer is reachable before invoking you.",
        "",
        f"Poll logs are available at {LOG_DIR / 'poll.log'} (and dated rotations in the same directory).",
        "If you encounter an unexpected error, read recent log entries for context.",
    ]
    return "\n".join(lines)


def _fetch_workable_videos() -> list | None:
    """Videos the agent can act on, oldest first, each with its own agent,
    model and effort. Stuck videos are already left out by the API.

    None when the request fails, and the caller then starts no pipeline session
    that pass. There is no unscoped fallback any more (TMDEV-129): without the
    list the poller cannot tell which agent a video belongs to, and a session
    told to "work every workable video" crosses agent boundaries (TMDEV-108).
    """
    import urllib.request
    import json as _json
    try:
        req = urllib.request.Request(f"{RENDERER_URL}/videos/workable")
        with urllib.request.urlopen(req, timeout=10) as resp:
            videos = _json.loads(resp.read().decode())
    except Exception as e:
        log.warning("Could not fetch workable videos: %s", e)
        return None
    return videos if isinstance(videos, list) else None


def _fetch_mining_urls() -> list[str]:
    """Fetch configured mining YouTube URLs from the Flask API. Returns [] on any error."""
    import urllib.request
    import json as _json
    try:
        with urllib.request.urlopen(f"{RENDERER_URL}/research/mining-sources", timeout=10) as r:
            return _json.loads(r.read()).get("youtube_urls", [])
    except Exception:
        return []


def _fetch_settings() -> dict:
    """GET /settings from the Flask API. Returns {} on any error (fail open)."""
    try:
        import urllib.request as _urllib
        import json as _json_mod
        with _urllib.urlopen(f"{RENDERER_URL}/settings", timeout=10) as r:
            return _json_mod.loads(r.read())
    except Exception:
        return {}


def _record_research_run(dry_run: bool = False) -> bool:
    """POST /research/record-run right before invoking a research agent session.

    Unlike the other HTTP helpers above, this fails CLOSED: if the API is
    unreachable, research is skipped this tick rather than invoking an
    uncapped agent session with no record of the attempt. A dry run logs the
    intent without making the request, matching invoke_agent's own dry-run
    behavior — a preview run should have zero side effects.
    """
    if dry_run:
        log.info("[DRY RUN] Would POST /research/record-run")
        return True
    import urllib.request
    try:
        req = urllib.request.Request(
            f"{RENDERER_URL}/research/record-run", method="POST", data=b"{}"
        )
        with urllib.request.urlopen(req, timeout=10):
            return True
    except Exception as e:
        log.error("Could not record research run — skipping research this tick: %s", e)
        return False


def _fetch_pending_script_profiles() -> list:
    """GET /script-profiles/pending. Returns [] on any error (fail open).

    Failing open is safe here: an empty list just means no profile is built
    this tick. The fail-*closed* half is _record_profile_attempt below, which
    is what stops an uncapped agent session running with no record of it.
    """
    import urllib.request
    import json as _json
    try:
        with urllib.request.urlopen(f"{RENDERER_URL}/script-profiles/pending", timeout=10) as r:
            return _json.loads(r.read())
    except Exception as e:
        log.warning("Could not fetch pending script profiles: %s", e)
        return []


def _record_profile_attempt(profile_id: str, dry_run: bool = False) -> str:
    """POST /script-profiles/<id>/record-attempt right before invoking the agent.

    Returns the profile's new status: "GENERATING" to proceed, "FAILED" when
    the attempt cap is exhausted (the server marks the row and stores the
    error — poll.py has no DB access and could not write a meaningful one),
    or "" when the request failed.

    Fails CLOSED, exactly like _record_research_run: an unreachable API means
    the profile is skipped this tick rather than invoking an agent session
    whose attempt nothing counted. A crashed agent leaves no completion to
    count, so a completion-counted cap would re-fire every tick forever.
    """
    if dry_run:
        log.info("[DRY RUN] Would POST /script-profiles/%s/record-attempt", profile_id)
        return "GENERATING"
    import urllib.request
    import json as _json
    try:
        req = urllib.request.Request(
            f"{RENDERER_URL}/script-profiles/{profile_id}/record-attempt",
            method="POST", data=b"{}",
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return _json.loads(resp.read()).get("status", "")
    except Exception as e:
        log.error("Could not record script-profile attempt — skipping profile %s "
                  "this tick: %s", profile_id, e)
        return ""


def build_script_profile_prompt(profile_id: str, name: str = "",
                                preferences: str = "") -> str:
    """The prompt that turns one profile's transcripts into style markdown.

    Carries only the profile id: the transcripts and the finished markdown both
    travel over MCP, never through poll.py, exactly as research topics travel
    via create_video() rather than being parsed out of agent stdout.
    """
    return "\n".join([
        f"[TUBEMATIC SCRIPT PROFILE — {_now_iso()}]",
        "",
        "Invoke the tubematic-create-script-writing-skill skill and build one script profile.",
        "",
        f"Profile id: {profile_id}" + (f"  (name: {name})" if name else ""),
        "",
        "Use the tubematic MCP tools to:",
        f"  1. Call get_script_profile_transcripts(\"{profile_id}\") to read the corpus",
        "  2. Analyse it per the skill and produce the style markdown plus a corpus summary",
        f"  3. Call complete_script_profile(\"{profile_id}\", markdown, corpus_summary)",
        "",
        "Do not advance any video, research any topic, or write any file during this run.",
        "",
        *_preferences_block(preferences, "building a script style profile from transcripts"),
        "IMPORTANT: Skip the operator skill setup checks (docker/curl health checks).",
        "The poller has already verified the renderer is reachable before invoking you.",
        "",
        f"Poll logs are available at {LOG_DIR / 'poll.log'} (and dated rotations in the same directory).",
        "If you encounter an unexpected error, read recent log entries for context.",
    ])


def build_research_prompt(strategies: list[str], preferences: str = "") -> str:
    lines = [
        f"[TUBEMATIC RESEARCH — {_now_iso()}]",
        "",
        "Invoke the tubematic-topic-research skill.",
        "",
        f"Active strategies: {','.join(strategies)}",
        "",
        "Research and propose new video topics using each active strategy.",
        "Use the tubematic MCP tools to:",
        "  1. Call get_research_strategies() to confirm active strategies",
        "  2. Call list_projects() to get the current project list",
        "  3. For curriculum: only enumerate sub-topics for projects where",
        "     is_curriculum_seed=1 AND status='active' AND expired is false.",
        "     Skip all others.",
        "  4. For each strategy, research and score topics (score >= 5 required)",
        "  5. Before creating a video: match it to an existing project via",
        "     list_projects(); only call upsert_project() if no project matches",
        "     at all. If the best match is paused or expired, SKIP the candidate:",
        "     do not file it into another project or create a new one for it.",
        "     Otherwise call list_project_topics() for that project and SKIP the",
        "     candidate if any topic there, archived or rejected ones included,",
        "     covers the same core mechanism.",
        "  6. Call create_video() for each qualifying topic",
        "  7. Call mark_research_done() when all strategies are complete",
        "     (records last-research-run time for display — does not gate scheduling)",
        "",
    ]
    settings = _fetch_settings()
    cur_cap   = settings.get("max_curriculum_per_run", 2)
    trend_cap = settings.get("max_trending_per_run", 2)
    mine_cap  = settings.get("max_mining_per_run", 2)
    trending_sources = settings.get("trending_sources", ["GitHub Trending", "Hacker News"])

    lines += [
        "Per-run topic targets (do not exceed):",
        f"  - curriculum: up to {cur_cap} new candidates per seed domain",
        f"  - trending:   up to {trend_cap} new candidates total",
    ]
    # Only when mining is active: the API drops it while no Gemini key is
    # stored, and a target line would invite a mining call that cannot work.
    if "mining" in strategies:
        lines.append(f"  - mining:     up to {mine_cap} new candidates total — mine_youtube_topics "
                     "files these itself, so call it once and file no extra mining topics")
    lines += [
        "Never set a topic to TOPIC_REJECTED: rejecting a topic is the human's decision.",
        "",
    ]
    if "trending" in strategies:
        src_block = "\n".join(f"  - {s}" for s in trending_sources) or "  (none configured)"
        lines += [
            "Trending strategy — scan ONLY these configured sources:",
            src_block,
            "",
        ]
    if "mining" in strategies:
        mining_urls = _fetch_mining_urls()
        url_block = (
            "\n".join(f"  - {u}" for u in mining_urls)
            if mining_urls
            else "  (none configured — add URLs via set_mining_sources or the Topics dashboard)"
        )
        lines += [
            "Mining strategy — call get_mining_sources(), then mine_youtube_topics(project_id=..., "
            "youtube_urls=[...]) once. It files at most the mining cap and skips topics that "
            "already exist; do not create extra mining topics yourself.",
            f"Configured YouTube URLs:\n{url_block}",
            "",
        ]
    lines += _preferences_block(preferences, "topic research")
    lines += [
        "IMPORTANT: Skip the operator skill setup checks (docker/curl health checks).",
        "The poller has already verified the renderer is reachable before invoking you.",
        "",
        f"Poll logs are available at {LOG_DIR / 'poll.log'} (and dated rotations in the same directory).",
        "If you encounter an unexpected error, read recent log entries for context.",
    ]
    return "\n".join(lines)


# ── Session bookkeeping (TMDEV-129) ─────────────────────────────────────────

def _post_outcome(video_id: str, start_status: str, session_key: str = "") -> dict | None:
    """POST /videos/<id>/agent-outcome. None if the report could not be made.

    The API, not this module, decides whether the session made progress: it
    compares the video's status now with the one the session started at, in
    one atomic UPDATE. The exit code is never the judge — Claude exits 0 on an
    unknown model, Codex exits 0 with every MCP call refused.

    The session key makes a re-report — a successor finishing a session whose
    supervisor died after reporting it — a no-op on the API's side.
    """
    import urllib.request
    body = {"start_status": start_status}
    if session_key:
        body["session_key"] = session_key
    try:
        req = urllib.request.Request(
            f"{RENDERER_URL}/videos/{video_id}/agent-outcome", method="POST",
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode() or "{}")
    except Exception as e:
        log.warning("Could not record this session's outcome — the no-progress count is "
                    "unchanged: %s", e)
        return None


def _score_session(session: _Session) -> str:
    """Record a finished pipeline session's outcome; return the video's status now.

    "" when the outcome could not be recorded. Fails open, like usage: missing
    one count delays a stuck flag by a session, it does not cost a pass.
    """
    outcome = _post_outcome(session.video_id, session.start_status, session.key)
    if outcome is None:
        return ""
    end = outcome.get("status") or ""
    if outcome.get("replayed"):
        log.info("This session's outcome was already recorded — not counted again")
        return end
    count = outcome.get("count") or 0
    if count:
        if session.runs == 0:
            why = "no agent process ran"
        elif session.returncode is None:
            why = "exit code unknown: the session outlived the supervisor that started it"
        else:
            why = f"exit code {session.returncode}" + (", timed out" if session.timed_out else "")
        # Non-zero is an ERROR; a clean exit that did nothing is the CLIs'
        # usual way of failing quietly, so it is a WARNING, not an INFO. An
        # unknown exit code (an adopted session) is a WARNING too.
        level = logging.WARNING if session.returncode in (0, None) else logging.ERROR
        log.log(level, "No progress: the video is still at %s after this session (%s) — "
                "%d session(s) in a row", session.start_status, why, count)
        if outcome.get("stuck"):
            log.error("The video is flagged stuck and will not be dispatched again until a "
                      "human changes its status or presses Retry agent on the dashboard")
    else:
        log.info("Progress: %s → %s", session.start_status, end)
        if end in OVERRUN.get(session.start_status, ()):
            log.warning("The session ran past its stage (%s → %s): its whole cost is "
                        "recorded as %s", session.start_status, end, session.start_status)
    return end


def _run_session(session: _Session, prompt: str, agent: dict, model: str,
                 effort: str) -> str:
    """A pool thread's whole job: run one session, then score it."""
    _current_session.set(session)
    try:
        log.info("Session started — agent %r, model %r, effort %r", agent.get("id"),
                 model or "<CLI default>", effort or "<CLI default>")
        invoke_agent(prompt, agent, model=model, effort=effort, operation=session.operation,
                     attribution=session.attribution)
    except Exception:
        log.exception("Session crashed inside the poller")
    end = _score_session(session) if session.video_id else ""
    # Only now: until the outcome is recorded, a successor supervisor must be
    # able to find this session and finish its bookkeeping.
    _registry_remove_session(session.key)
    return end


def _finish_orphan(entries: list, agents_by_id: dict) -> str:
    """Bookkeeping for a session whose supervisor died before it was done.

    `entries` are the session's registry entries, one per agent process. Any
    run whose usage was not recorded yet is recorded from its output files,
    under the run id it was registered with, so a run the dead supervisor had
    already reported is not counted twice. The session is then scored once.
    The effort/model retry chain is not resumed: the runs that happened are the
    session.
    """
    first = entries[0]
    session = _Session(first.get("lane") or "pipeline", first.get("label") or "orphan",
                       video_id=first.get("video_id") or "",
                       start_status=first.get("start_status") or "",
                       profile_id=first.get("profile_id") or "",
                       agent_id=first.get("agent_id") or "", model=first.get("model") or "",
                       operation=first.get("operation") or "agent_pipeline",
                       attribution=first.get("attribution") or ())
    session.runs = len(entries)
    # Its own key, not a new one: the dead supervisor may already have
    # reported this outcome, and the API skips a key it has seen.
    session.key = first.get("session_key") or session.key
    _current_session.set(session)
    log.warning("Finishing the bookkeeping for a session left behind by a supervisor that "
                "died (pid %s)", ", ".join(str(e.get("pid")) for e in entries))
    agent = agents_by_id.get(session.agent_id)
    adapter = ADAPTERS.get(session.agent_id)
    binary = resolve_agent_binary(agent) if agent is not None and adapter is not None else None
    for entry in entries:
        if entry.get("usage_done"):
            continue
        stdout = _read(Path(entry.get("stdout") or "/nonexistent"))
        stderr = _read(Path(entry.get("stderr") or "/nonexistent"))
        if binary:
            if stdout.strip():
                log.info("%s", adapter.summarize_output(stdout))
            if stderr:
                log.warning("Agent stderr:\n%s", clip(stderr.strip(), keep="tail"))
            _report_usage(adapter, binary, resolve_agent_cwd(agent), entry.get("model") or "",
                          _Result(-1, stdout, stderr),
                          {"operation": session.operation, "videos": session.attribution},
                          session_id=entry.get("run_id") or "")
        if entry.get("run_id"):
            _registry_run_done(entry["run_id"])
    end = _score_session(session) if session.video_id else ""
    _registry_remove_runs(entries)
    return end


def _touch_heartbeat() -> None:
    try:
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        HEARTBEAT.touch()
    except OSError as e:
        log.warning("Could not touch %s: %s", HEARTBEAT, e)


def _check_heartbeat() -> None:
    """Called by a tick that found the lock held. Logs; never kills."""
    try:
        age = time.time() - HEARTBEAT.stat().st_mtime
    except OSError:
        return
    if age > HEARTBEAT_STALE_SECS:
        log.error("A supervisor holds the poll lock but has not touched %s for %d min — it "
                  "may be hung. Not killing it: one of its sessions may be in the middle of a "
                  "paid call. Inspect it with: ps -ef | grep poll.py", HEARTBEAT, age // 60)


def _setting_int(settings: dict, key: str, default: int, lo: int, hi: int | None) -> int:
    try:
        value = int(settings.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value >= lo and (hi is None or value <= hi) else default


# ── Supervisor (TMDEV-129) ───────────────────────────────────────────────────

class _Supervisor:
    """The loop the lock holder runs until there is nothing left to do.

    Three lanes: the pipeline lane runs up to max_concurrent_agent_sessions
    sessions, one video and one stage each; research and script profiles run
    beside it, outside that cap, one session each. Every pass re-reads the
    pipeline status and settings, so nothing here needs a restart.
    """

    def __init__(self, dry_run: bool):
        self.dry_run = dry_run
        # Sized for the ceiling, so a raised setting takes effect at once.
        self.pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=MAX_SESSIONS_CEILING + 3, thread_name_prefix="session")
        self.running: dict = {}          # key -> (_Session, Future)
        # Sessions a dead supervisor left behind, one group of registry
        # entries per session: {"key", "entries", "meta", "term_sent_at", "kill_sent"}.
        self.adopted: list = []
        self.gone: list = []             # ...groups that finished while none was running
        self.agents_by_id: dict = {}     # from the last pass; orphan bookkeeping needs it
        self.cooldown: dict = {}         # video_id -> monotonic time it may be dispatched again
        self.research_done = False       # research runs at most once per supervisor
        self.said: set = set()           # keys of messages already logged this supervisor
        self.dispatched = False
        self.paused = False

    # ── helpers ──
    def _once(self, key: str, level: int, msg: str, *args) -> None:
        """Log a condition once per supervisor, not once per pass."""
        if key not in self.said:
            self.said.add(key)
            log.log(level, msg, *args)

    def _pipeline_in_flight(self) -> set:
        ids = {s.video_id for s, _ in self.running.values() if s.lane == "pipeline"}
        return ids | {g["meta"].get("video_id") for g in self.adopted
                      if g["meta"].get("lane") == "pipeline"}

    def _lane_busy(self, lane: str) -> bool:
        """Research and profiles are single-instance lanes, an adopted orphan included."""
        return lane in self.running or any(g["meta"].get("lane") == lane for g in self.adopted)

    def _busy(self) -> bool:
        return bool(self.running or self.adopted)

    def _cooling(self) -> bool:
        now = time.monotonic()
        self.cooldown = {v: t for v, t in self.cooldown.items() if t > now}
        return bool(self.cooldown)

    def _start(self, key: str, session: _Session, prompt: str, agent: dict, model: str,
               effort: str, timeout: int) -> None:
        self.dispatched = True
        if self.dry_run:
            log.info("[DRY RUN] Would start a session for %s", session.label)
            invoke_agent(prompt, agent, dry_run=True, model=model, effort=effort)
            return
        session.deadline = time.time() + timeout
        log.info("Starting a session for %s (%d running)", session.label, len(self.running) + 1)
        # A fresh Context per session, so the session a pool thread last worked
        # for can never label the next one's log lines.
        future = self.pool.submit(contextvars.Context().run, _run_session, session, prompt,
                                  agent, model, effort)
        self.running[key] = (session, future)

    # ── the loop ──
    def run(self) -> int:
        try:
            if not self.dry_run:
                self._adopt()
            while True:
                if not self.dry_run:
                    _touch_heartbeat()
                self._reap()
                self.dispatched = False
                code = self._pass()
                if self.dry_run:
                    return code or 0
                if not self._busy() and not self.dispatched:
                    if code is not None:
                        return code
                    # A cooldown is only worth waiting out if a session could
                    # follow it. Paused, none can — and the lock this process
                    # holds is what upgrade.py and service.py wait for.
                    if self.paused or not self._cooling():
                        return 0
                self._wait()
        finally:
            self.pool.shutdown(wait=True)

    def _wait(self) -> None:
        timeout = LOOP_WAIT_SECS
        if self._cooling():
            soonest = min(self.cooldown.values()) - time.monotonic()
            timeout = max(1.0, min(timeout, soonest))
        futures = [f for _, f in self.running.values()]
        if not self.adopted:
            if futures:
                concurrent.futures.wait(futures, timeout=timeout,
                                        return_when=concurrent.futures.FIRST_COMPLETED)
            else:
                time.sleep(timeout)
            return
        # Adopted sessions are not our children, so nothing wakes us when one
        # ends; look every second instead. That is also what keeps a timed-out
        # orphan's SIGKILL on KILL_GRACE_SECS rather than on the next pass.
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if any(f.done() for f in futures) or self._tend_adopted():
                return
            time.sleep(1)

    def _reap(self) -> None:
        for key, (session, future) in list(self.running.items()):
            if not future.done():
                continue
            del self.running[key]
            try:
                end = future.result()
            except Exception:  # _run_session catches everything; belt and braces
                log.exception("Session %s ended with an error", session.label)
                end = ""
            self._maybe_cool(session.video_id, session.start_status, end)

    def _maybe_cool(self, video_id: str, start_status: str, end: str) -> None:
        # The session may still hold the video's scene-work claim, which the
        # MCP server keeps for CLAIM_COOLDOWN_SECS after its last use. An
        # unknown end status ("") is treated as still inside the window.
        if video_id and start_status in CLAIM_STATUSES and (not end or end in CLAIM_STATUSES):
            self.cooldown[video_id] = time.monotonic() + CLAIM_COOLDOWN_SECS
            log.info("Video %s waits %d min before its next session: the last one's "
                     "scene-work claim is still live", video_id, CLAIM_COOLDOWN_SECS // 60)

    # ── orphans ──
    def _adopt(self) -> None:
        """Group the registry by session; adopt what is still running."""
        groups: dict = {}
        for e in _registry_read():
            if e.get("pid"):
                groups.setdefault(e.get("session_key") or f"pid:{e['pid']}", []).append(e)
        for key, entries in groups.items():
            group = {"key": key, "entries": entries, "meta": entries[0]}
            if self._running_or_overdue(group):
                log.warning("Adopting %s (pid %s), left running by a supervisor that died",
                            group["meta"].get("label"),
                            ", ".join(str(e["pid"]) for e in entries))
                self.adopted.append(group)
            else:
                # Finished while no supervisor was running: its usage and
                # outcome still need recording, which needs the agents list,
                # so that happens on the first pass.
                self.gone.append(group)

    @staticmethod
    def _running_or_overdue(group: dict) -> bool:
        leaders = [e for e in group["entries"] if _proc_start(e["pid"]) == e.get("proc_start")]
        deadline = group["meta"].get("deadline")
        overdue = deadline is not None and time.time() >= deadline
        return bool(leaders) or (overdue and any(_entry_group_alive(e) for e in group["entries"]))

    def _tend_adopted(self) -> bool:
        """Finish ended orphans and stop overdue ones. True if one was finished."""
        for group in self.gone:
            self._finish(group)
        finished = bool(self.gone)
        self.gone = []
        now = time.time()
        for group in list(self.adopted):
            entries = group["entries"]
            alive = [e["pid"] for e in entries if _entry_group_alive(e)]
            deadline = group["meta"].get("deadline")
            overdue = deadline is not None and now >= deadline
            if group.get("term_sent_at") is not None or (overdue and alive):
                # The same SIGTERM-then-SIGKILL as a session this supervisor
                # started, against the whole group: its leader exiting does not
                # end it while a child that ignored SIGTERM is still running.
                if not alive:
                    self.adopted.remove(group)
                    self._finish(group)
                    finished = True
                    continue
                if group.get("term_sent_at") is None:
                    sig = signal.SIGTERM
                    group["term_sent_at"] = now
                elif now - group["term_sent_at"] >= KILL_GRACE_SECS and not group.get("kill_sent"):
                    sig = signal.SIGKILL
                    group["kill_sent"] = True
                else:
                    continue
                log.error("Adopted session %s passed agent_session_timeout_secs — sending %s to "
                          "its process group", group["meta"].get("label"), sig.name)
                for pid in alive:
                    try:
                        os.killpg(pid, sig)
                    except ProcessLookupError:
                        pass
                continue
            if not any(_proc_start(e["pid"]) == e.get("proc_start") for e in entries):
                self.adopted.remove(group)
                self._finish(group)
                finished = True
        return finished

    def _finish(self, group: dict) -> None:
        # Its usage fetch can take minutes, so it runs on the pool like any
        # session rather than stalling the loop (and the heartbeat). The
        # registry entries go only once it is done.
        meta = group["meta"]
        key = f"orphan:{group['key']}"
        session = _Session(meta.get("lane") or "pipeline", meta.get("label") or key,
                           video_id=meta.get("video_id") or "",
                           start_status=meta.get("start_status") or "")
        future = self.pool.submit(contextvars.Context().run, _finish_orphan,
                                  group["entries"], self.agents_by_id)
        self.running[key] = (session, future)

    # ── one pass ──
    def _pass(self) -> int | None:
        """Start whatever each lane has room for. An int means "stop if idle"."""
        status = _fetch_pipeline_status()
        if not status:
            log.error("Flask API unreachable — nothing started this pass.")
            return 1
        agents = _fetch_agents()
        if agents is None:
            log.error("Could not read the installed agents — nothing started this pass.")
            return 1
        agents_by_id = {a.get("id"): a for a in agents}
        self.agents_by_id = agents_by_id
        if not self.dry_run:
            self._tend_adopted()
        default = _default_agent(agents)
        if default is None:
            self._once("no-agent", logging.WARNING, "No agent installed — nothing can run. "
                       "Run: python onboard.py --install-agent <agent>")
            return 0

        # Read lazily, at most once a pass, and only by a lane that is about to
        # start something — an idle pass stays two requests.
        cache: dict = {}

        def settings() -> dict:
            if "s" not in cache:
                cache["s"] = _fetch_settings()
                if not cache["s"]:
                    log.warning("Could not read /settings — using the defaults, and no user "
                                "preferences, this pass")
            return cache["s"]

        def timeout() -> int:
            return _setting_int(settings(), "agent_session_timeout_secs",
                                DEFAULT_SESSION_TIMEOUT, 60, None)

        def preferences() -> str:
            return settings().get("user_preferences", "") or ""

        self._profiles(status, default, timeout, preferences)
        self.paused = bool(status.get("paused"))
        if self.paused:
            self._once("paused", logging.INFO, "Pipeline is paused — starting no pipeline or "
                       "research session; sessions already running finish")
            return None
        self.said.discard("paused")
        self._pipeline(status, agents_by_id, default, settings, timeout, preferences)
        self._research(status, default, timeout, preferences)
        return None

    def _profiles(self, status, default, timeout, preferences) -> None:
        # Above the pause guard on purpose: building a profile spends no
        # ElevenLabs credit and produces no video, so blocking it while paused
        # would leave a dashboard row stuck at PENDING with nothing saying why.
        if self._lane_busy("profile") or not status.get("pending_script_profiles"):
            return
        for profile in _fetch_pending_script_profiles():
            outcome = _record_profile_attempt(profile["id"], dry_run=self.dry_run)
            if outcome == "GENERATING":
                log.info("Building script profile %s (%r) — attempt recorded",
                         profile["id"], profile.get("name", ""))
                session = _Session("profile", f"profile={profile['id']}",
                                   profile_id=profile["id"], agent_id=default.get("id", ""),
                                   model=_default_model(default), operation="agent_profile")
                self._start("profile", session,
                            build_script_profile_prompt(profile["id"], profile.get("name", ""),
                                                        preferences=preferences()),
                            default, _default_model(default), _default_effort(default),
                            timeout())
                return
            if outcome == "FAILED":
                # Cap exhausted — the server marked the row and stored the
                # error. Try the next pending profile, if any.
                log.warning("Script profile %s exhausted its attempts and was marked FAILED",
                            profile["id"])
                continue
            # "" — the attempt could not be recorded. Fail closed: no session
            # runs without its attempt counted.
            return

    def _pipeline(self, status, agents_by_id, default, settings, timeout, preferences) -> None:
        if not status.get("workable_count"):
            return
        busy = self._pipeline_in_flight()
        cap = _setting_int(settings(), "max_concurrent_agent_sessions", DEFAULT_MAX_SESSIONS,
                           1, MAX_SESSIONS_CEILING)
        free = cap - len(busy)
        if free <= 0:
            return
        videos = _fetch_workable_videos()
        if videos is None:
            return
        self._cooling()   # prunes expired cooldowns
        for video in videos:
            if free <= 0:
                break
            vid, st = video.get("id"), video.get("status") or ""
            if not vid or vid in busy or vid in self.cooldown:
                continue
            if st not in STAGES:
                self._once(f"stage:{vid}:{st}", logging.ERROR,
                           "Video %s is at %s, which has no agent stage — skipped", vid, st)
                continue
            agent = _video_agent(video, agents_by_id, default, quiet=f"agent:{vid}" in self.said)
            self.said.add(f"agent:{vid}")
            if agent is None:
                continue
            model = (video.get("agent_model") or "").strip() or _default_model(agent)
            effort = (video.get("agent_effort") or "").strip() or _default_effort(agent)
            # The status the video is at now is the stage the session's usage
            # is recorded under — exact now that a session is one stage.
            session = _Session("pipeline", f"video={vid}", video_id=vid, start_status=st,
                               agent_id=agent.get("id", ""), model=model,
                               operation="agent_pipeline",
                               attribution=[{"video_id": vid, "stage": st}])
            self._start(f"video:{vid}", session,
                        build_pipeline_prompt(vid, st, preferences=preferences()),
                        agent, model, effort, timeout())
            busy.add(vid)
            free -= 1

    def _research(self, status, default, timeout, preferences) -> None:
        if self.research_done or self._lane_busy("research"):
            return
        proposed_count = status.get("proposed_count", 0)
        runs_today     = status.get("research_runs_today", 0)
        max_runs       = status.get("max_research_runs_per_day", 8)
        # No env fallback any more (TMDEV-73): the settings table is the only
        # source, and /pipeline/status already merges in the spec default.
        pending_cap    = status.get("research_pending_cap", 15)
        # Two independent gates: pending_cap bounds queue breadth, max_runs
        # bounds attempt frequency/cost (a day where research keeps coming up
        # dry can't burn an unbounded number of agent sessions).
        if proposed_count >= pending_cap:
            self._once("research-pending", logging.INFO,
                       "Skipping research — %d topics already pending (cap=%d). "
                       "Approve some topics first.", proposed_count, pending_cap)
            return
        if runs_today >= max_runs:
            self._once("research-runs", logging.INFO,
                       "Skipping research — %d run(s) in the last 24h (cap=%d).",
                       runs_today, max_runs)
            return
        strategies = status.get("active_strategies", ["curriculum", "trending", "mining"])
        # The API leaves mining out while no Gemini key is stored (TMDEV-165),
        # so an install whose only strategy was mining has nothing to research.
        # Checked before the run is recorded: a session with nothing to do
        # would still spend a slot of the daily cap.
        if not strategies:
            self._once("research-none", logging.INFO,
                       "Skipping research — no research strategy is active.")
            return
        # At most once per supervisor, whether or not the record succeeds: a
        # supervisor lives as long as there is work, and a research run per
        # finished session would spend the daily cap back to back.
        self.research_done = True
        if not _record_research_run(dry_run=self.dry_run):
            return
        log.info("Research run — strategies: %s", ",".join(strategies))
        session = _Session("research", "research", agent_id=default.get("id", ""),
                           model=_default_model(default), operation="agent_research")
        self._start("research", session,
                    build_research_prompt(strategies, preferences=preferences()),
                    default, _default_model(default), _default_effort(default), timeout())


# ── Main ─────────────────────────────────────────────────────────────────────

class _ApiAuth(urllib.request.BaseHandler):
    """Adds the API's bearer token to every request for RENDERER_URL (TMDEV-152).

    One opener covers every urlopen call in this module. The file is read per
    request rather than once, because the supervisor outlives a token rotation;
    and the header goes to the API only, never to any other URL.
    """

    def http_request(self, req):
        from tubematic_core.auth import SecretMissing, read_secret
        if req.full_url.startswith(RENDERER_URL.rstrip("/") + "/"):
            try:
                req.add_unredirected_header("Authorization", f"Bearer {read_secret('api_token')}")
            except SecretMissing:
                pass  # the API answers 401, which is logged where the call is made
        return req

    https_request = http_request


def install_api_auth() -> bool:
    """Install the token-adding opener. False, logged, when there is no token."""
    from tubematic_core.auth import SecretMissing, read_secret
    try:
        read_secret("api_token")
    except SecretMissing as e:
        log.error("Cannot call the API without its token: %s. Run: python upgrade.py "
                  "(or python onboard.py --step auth)", e)
        return False
    urllib.request.install_opener(urllib.request.build_opener(_ApiAuth()))
    return True


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    _start  = time.monotonic()

    _setup_logging(dry_run)
    log.info("Poll started (dry_run=%s)", dry_run)
    if not install_api_auth():
        sys.exit(1)
    stale = _legacy_flags(sys.argv)
    if stale:
        log.warning("Ignoring %s from an older crontab — the agent is resolved per video "
                    "now. Re-run: python onboard.py --step cron", ", ".join(stale))

    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    lock_fh = open(LOCKFILE, "w")
    try:
        fcntl.flock(lock_fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        # flock dies with its holder, so a held lock is a live supervisor.
        _check_heartbeat()
        log.info("A supervisor is already running. Exiting.")
        lock_fh.close()
        sys.exit(0)

    try:
        code = _Supervisor(dry_run).run()
    finally:
        log.info("Poll completed in %.2fs", time.monotonic() - _start)
        fcntl.flock(lock_fh, fcntl.LOCK_UN)
        lock_fh.close()
        # The file is left in place on purpose. Unlinking a flock'd file lets a
        # poller still holding the old inode and one that creates a fresh file
        # both believe they hold the lock.
    if code:
        sys.exit(code)


if __name__ == "__main__":
    main()
