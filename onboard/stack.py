"""Stack control shared by upgrade.py and scripts/service.py (TMDEV-96).

Nothing here prompts. Every mutation goes through the Executor, so --dry-run
works end to end; every read (docker inspect, crontab -l, the database) is
done directly, so a dry run reports the machine as it really is.

The container, directory and volume logic is not re-implemented here: it is
imported from onboard/actions.py, which onboarding also uses. A second copy
of the volume reconciliation or the compose prefix is exactly the drift this
repo has been bitten by before.
"""
import fcntl
import json
import os
import sqlite3
import subprocess
from contextlib import contextmanager
from pathlib import Path

from onboard.actions import (
    REPO_ROOT, _await_health, _compose, _reconcile_volume_devices, _stale_volumes,
    apply_directories,
)
from onboard.config import DB_PATH, POLL_LOG_DIR
from onboard.executor import Executor, Reporter

# The lock scripts/poll.py's supervisor holds for as long as it runs, its
# agent sessions included (TMDEV-129). Keep in sync: scripts/poll.py LOCKFILE.
# Taking the same lock is what lets an upgrade see a running agent — and, held
# for the whole upgrade, stops cron from starting one mid-way (poll.py exits
# when the lock is taken).
LOCK_PATH = POLL_LOG_DIR.parent / "poll.lock"

# Every agent process the poller has running, so a session that outlives a
# dead supervisor is still visible. Keep in sync: scripts/poll.py REGISTRY.
SESSIONS_REGISTRY = POLL_LOG_DIR.parent / "poll-sessions.json"

SERVICES = ("tubematic-api", "tubematic-mcp", "tubematic-renderer", "tubematic-dashboard")


# ── In-flight work ───────────────────────────────────────────────────────────

@contextmanager
def poll_lock(path: Path = None):
    """Try poll.py's lock without waiting; yield whether it was acquired.

    The file is never unlinked: unlinking a flock'd file lets two holders each
    lock a different inode and both believe they hold the lock. Opening it is
    not routed through the Executor — creating an empty lock file is not a
    change a dry run needs to preview, and the lock must really be taken for
    the dry run's gate to report truthfully.
    """
    path = Path(path) if path else LOCK_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "a")
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    finally:
        fh.close()


def _proc_start(pid: int):
    """A live process's start time from /proc, or None if it is gone or a
    zombie. Keep in sync: scripts/poll.py _proc_start — (pid, start time) names
    one process for good, where a pid alone can be reused."""
    try:
        stat = Path(f"/proc/{pid}/stat").read_text()
    except OSError:
        return None
    fields = stat.rsplit(")", 1)[-1].split()
    if len(fields) < 20 or fields[0] == "Z":
        return None
    return fields[19]


def orphan_sessions(path: Path = None) -> list:
    """Agent sessions a dead poller left running, as human-readable reasons.

    Only meaningful with the poll lock held: a live supervisor owns every entry
    in the registry, and the lock already reports it. With the lock free, a
    live entry is an orphan — it holds no lock, and stopping the stack would
    pull the MCP server out from under it mid-session.
    """
    path = Path(path) if path else SESSIONS_REGISTRY
    try:
        entries = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    reasons = []
    for e in entries if isinstance(entries, list) else []:
        if not isinstance(e, dict) or not isinstance(e.get("pid"), int):
            continue
        start = _proc_start(e["pid"])
        if start is not None and start == e.get("proc_start"):
            reasons.append(f"an agent session ({e.get('label') or 'unknown'}, pid {e['pid']}) is "
                           f"still running, left behind by a poller that stopped")
    return reasons


def _unreadable(db_path: Path, err: Exception) -> str:
    return (f"cannot read the database at {db_path} as this user — run as its owner "
            f"(or with sudo). WAL mode needs write access to the database's sidecar "
            f"files even to read it. ({err})")


def in_flight(db_path: Path = DB_PATH) -> list:
    """Human-readable reasons a stop would kill work that costs money to redo.

    - RENDERING: the worker counts a killed render as a failure, and with the
      default retry budget of 1 that can escalate the video to FAILED.
    - VOICING: ElevenLabs may already have billed the audio, and nothing
      reconciles VOICING on restart. A VOICING video is often just waiting for
      the next tick, but an interactive agent session voicing it does not take
      poll.lock, so the status is the only signal there is.
    - PUBLISHING with a publication row whose post id is still empty: the
      upload is running inside a Flask request, which a stop kills. Also
      PUBLISHING with no rows at all: before 1.0.1 the rows were written only
      after the upload, so that is what an in-progress upload looks like on
      the install being upgraded. Current code writes them in the claim's
      transaction, so nothing else produces that state.

    An unreadable database is itself a reason — nothing can be verified.
    """
    db_path = Path(db_path)
    if not db_path.exists():
        return []
    try:
        con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        try:
            working = con.execute(
                "SELECT id, status, COALESCE(NULLIF(title, ''), topic) FROM videos "
                "WHERE status IN ('RENDERING', 'VOICING') ORDER BY id").fetchall()
            uploading = con.execute(
                "SELECT v.id, COALESCE(NULLIF(v.title, ''), v.topic) FROM videos v "
                "WHERE v.status = 'PUBLISHING' AND ("
                " EXISTS (SELECT 1 FROM video_publications p"
                "         WHERE p.video_id = v.id AND p.postforme_post_id = '')"
                " OR NOT EXISTS (SELECT 1 FROM video_publications p WHERE p.video_id = v.id))"
                " ORDER BY v.id").fetchall()
        finally:
            con.close()
    except sqlite3.Error as e:
        return [_unreadable(db_path, e)]

    why = {
        "RENDERING": "a render in progress — stopping it counts as a render failure",
        "VOICING": "voicing — stopping mid-voicing can lose audio ElevenLabs already billed",
    }
    reasons = [f"{vid} is {status} ({name}): {why[status]}" for vid, status, name in working]
    reasons += [f"{vid} is PUBLISHING ({name}): its upload has not finished"
                for vid, name in uploading]
    return reasons


def gate(db_path: Path, *, lock_acquired: bool, force: bool, rep: Reporter,
         registry: Path = None) -> bool:
    """True when it is safe to stop the stack (or --force said to anyway)."""
    # The poller holds the lock for as long as it runs — through a short wait
    # between sessions too, not only while an agent is working. Pausing the
    # pipeline makes it exit as soon as its running sessions finish.
    reasons = orphan_sessions(registry) if lock_acquired else [
        f"the scheduled poller is running ({LOCK_PATH} is held) — pause the pipeline to have it "
        f"stop once its running sessions finish"]
    reasons += in_flight(db_path)
    if not reasons:
        rep.ok("No work in flight")
        return True
    for r in reasons:
        rep.warn(r)
    if force:
        rep.warn("--force: continuing anyway")
        return True
    rep.info("Wait for it to finish and re-run, or pass --force to stop it regardless.")
    return False


# ── Stop / start ─────────────────────────────────────────────────────────────

def stop(ex: Executor, rep: Reporter, services=()) -> None:
    """`docker compose stop` — never `down`, and never `down -v`. Stopped
    containers keep their state, and nothing about the volumes changes."""
    services = list(services)
    r = ex.run([*_compose(), "stop", *services], cwd=REPO_ROOT)
    if r.returncode != 0:
        rep.fail("docker compose stop failed", (r.stderr or "").strip())
    rep.ok(f"Stopped {', '.join(services)}" if services else "Stack stopped")


def _container_state(name: str) -> tuple:
    """(status, health) — health is "" for a container without a healthcheck,
    and status is "" when there is no such container. Raises FileNotFoundError
    when docker itself is missing."""
    r = subprocess.run(
        ["docker", "inspect", "--format",
         "{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}", name],
        capture_output=True, text=True)
    if r.returncode != 0:
        return "", ""
    parts = r.stdout.split()
    return (parts[0] if parts else ""), (parts[1] if len(parts) > 1 else "")


def start(ex: Executor, rep: Reporter, services=(), *, confirm_down) -> None:
    """Directories, then volume reconciliation, then `up -d`, then health.

    The order is load-bearing. The volumes are `local`-driver binds, which do
    not create a missing device path — the mount fails outright. And a volume
    whose device moved must be dropped before `up`: Compose only prompts
    about it, and non-interactively the answer is no.

    Reconciling runs `docker compose down`, which takes down *every*
    container, whatever `services` names. So when it would, and something is
    still running, `confirm_down(running_names)` must say yes first — callers
    pass their in-flight gate, and a caller that has already stopped the
    stack passes `lambda names: True`. Required on purpose: forgetting it
    would let a one-service start kill a render. After a reconcile every
    service is brought back, not only the named ones.
    """
    services = list(services)
    apply_directories(None, ex, rep)
    if _stale_volumes():
        running = [n for n in SERVICES if _container_state(n)[0] == "running"]
        if running and not confirm_down(running):
            rep.fail("Not started: re-pointing the moved Docker volumes would take down the "
                     "whole stack while work is in flight.",
                     "Wait for it to finish, or re-run with --force.")
        services = []
    _reconcile_volume_devices(ex, rep)
    # Compose refuses to start a service whose token file is missing (TMDEV-152).
    ex.ensure_secrets()
    r = ex.run([*_compose(), "up", "-d", *services], cwd=REPO_ROOT)
    if r.returncode != 0:
        rep.fail("docker compose up failed", (r.stderr or "").strip())
    if ex.dry_run:
        rep.info("[dry-run] would wait for the health checks")
        return

    # Every service with a healthcheck is waited on; one that fails it, or a
    # renderer that is not running, fails the start rather than warning —
    # callers report success from the exit code.
    wanted = services or list(SERVICES)
    for name, url in (("tubematic-api", "http://localhost:4000"),
                      ("tubematic-mcp", "http://localhost:4100/mcp"),
                      ("tubematic-dashboard", "http://localhost:3000")):
        if name in wanted and not _await_health(name, url, rep):
            rep.fail(f"{name} did not become healthy", f"Run: docker compose logs {name}")
    if "tubematic-renderer" in wanted:
        status, _ = _container_state("tubematic-renderer")
        if status != "running":
            rep.fail(f"tubematic-renderer is {status or 'missing'}, not running",
                     "Run: docker compose logs tubematic-renderer")
        rep.ok("tubematic-renderer running")


# ── Cron ─────────────────────────────────────────────────────────────────────

def read_crontab() -> str:
    """The current user's crontab, or "" when there is none (or no crontab)."""
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    except FileNotFoundError:
        return ""
    return r.stdout if r.returncode == 0 else ""


def poll_cron_line(crontab: str):
    """The line apply_cron writes, or None."""
    return next((ln for ln in crontab.splitlines()
                 if "scripts/poll.py" in ln and not ln.lstrip().startswith("#")), None)


def _poll_token(line):
    if not line:
        return None
    return next((t for t in line.split() if t.endswith("/scripts/poll.py")), None)


def install_dir_of(line):
    """The install directory a poll line runs from — apply_cron writes
    `<python> <install>/scripts/poll.py`, both absolute."""
    token = _poll_token(line)
    return Path(token).parent.parent if token else None


def python_of(line):
    """The interpreter a poll line runs — the token just before poll.py."""
    token = _poll_token(line)
    if not token:
        return None
    parts = line.split()
    idx = parts.index(token)
    return parts[idx - 1] if idx > 0 else None


# ── Report ───────────────────────────────────────────────────────────────────

def report(rep: Reporter, *, db_path: Path = DB_PATH, repo_root: Path = REPO_ROOT,
           mode: str = "") -> bool:
    """Read-only readout: version, schema, cron, containers, in-flight work.
    Returns True when nothing needs attention.

    What a person runs when unsure an upgrade worked, so it must survive a
    half-configured install: each missing piece is reported, never raised.
    """
    from tubematic_core import db as tdb
    from tubematic_core.version import version

    healthy = True
    rep.info(f"Version {version()}" + (f" ({mode} install)" if mode else "") + f" at {repo_root}")

    # Schema
    db_path = Path(db_path)
    available = max((m.version for m in tdb.discover()), default=0)
    if not db_path.exists():
        rep.warn(f"No database at {db_path} — not installed yet? Run: python onboard.py")
        healthy = False
    else:
        try:
            applied = tdb.current_schema_version(db_path)
        except sqlite3.Error as e:
            rep.warn(_unreadable(db_path, e))
            healthy = False
        else:
            if applied == available:
                rep.ok(f"Database schema {applied:04d} (latest this version knows: {available:04d})")
            elif applied > available:
                # Older code may not understand a renamed or dropped column,
                # which is why rollback restores the matching backup.
                rep.warn(f"Database schema {applied:04d} is newer than this version understands "
                         f"({available:04d}) — this install is older than the database. Restore "
                         "the matching backup or run the newer version (see Rollback policy)")
                healthy = False
            else:
                rep.warn(f"Database schema {applied:04d}, this version ships {available:04d} — "
                         "the containers apply the rest when they start")
                healthy = False

    # Cron
    line = poll_cron_line(read_crontab())
    if not line:
        rep.warn("No Tubematic cron entry — the pipeline will not advance. "
                 "Run: python upgrade.py (or python onboard.py --step cron)")
        healthy = False
    else:
        target = install_dir_of(line)
        python = python_of(line)
        if target is None or Path(target).resolve() != Path(repo_root).resolve():
            rep.warn(f"The cron entry runs a different install: {target}. "
                     "Run: python upgrade.py from this directory")
            healthy = False
        elif not python or not os.path.exists(python):
            rep.warn(f"The cron entry's interpreter does not exist: {python}")
            healthy = False
        else:
            rep.ok(f"Cron entry runs this install ({python})")

    # Containers
    try:
        for name in SERVICES:
            status, health = _container_state(name)
            if not status:
                rep.warn(f"{name}: no such container")
                healthy = False
            elif status != "running" or health not in ("", "healthy"):
                rep.warn(f"{name}: {status}{' / ' + health if health else ''}")
                healthy = False
            else:
                rep.ok(f"{name}: running{' / healthy' if health else ''}")
    except FileNotFoundError:
        rep.warn("docker is not installed or not on PATH — container state unknown")
        healthy = False

    # In-flight work — information, not a fault
    for reason in in_flight(db_path):
        rep.info(f"In flight: {reason}")

    return healthy
