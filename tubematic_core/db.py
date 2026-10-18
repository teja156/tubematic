"""Schema ownership for every Tubematic process (TMDEV-91).

Before this module, four places defined the schema: renderer/api/pipeline.py's
_init_db, mcp/server.py's _init_db, onboard/actions.py's _SCHEMA and
scripts/clear_db.py's inline DDL. Two of them were already stale, and the two
that were not differed by three statements that the cross-copy test did not
look at. This is the one definition.

Every process calls migrate(). That is deliberate and is NOT the same as every
process owning schema logic: the definition lives in migrations/, and a
concurrent call is a cheap no-op read because the run holds a write lock. The
alternative — only the API migrates, everyone else asserts — would break the
VQA flow, where MCP tools are driven from a host shell with no Flask running.

Stdlib only. This module is imported by four processes with four different
dependency sets.
"""
import dataclasses
import importlib.util
import os
import pathlib
import re
import sqlite3
import stat
import time
from datetime import datetime, timezone

MIGRATIONS_DIR = pathlib.Path(__file__).resolve().parent / "migrations"

# _ensure_wal: measured against a brand-new file with 4 concurrent threads,
# 17/100 attempts hit the race with no retry at all. These are sized for
# surviving that first-creation window, not for steady-state contention — see
# _ensure_wal's docstring.
_WAL_SWITCH_ATTEMPTS = 5
_WAL_SWITCH_BACKOFF_SECS = 0.01

_FILENAME = re.compile(r"^(\d{4,})_([A-Za-z0-9_]+)\.(sql|py)$")


class MigrationError(RuntimeError):
    """Raised for failures specific to discovering or applying migrations —
    a duplicate version number, a migration with no up(), a migration that
    raised, a backup that could not be written. Not every failure this module
    can raise: connect()'s mkdir can still raise OSError on a read-only
    filesystem, discover()'s directory scan can still raise FileNotFoundError
    on a missing migrations directory, and a corrupt database file can still
    raise sqlite3.DatabaseError. Those are left unwrapped rather than folded
    in here, since a caller may well want to tell "this isn't a database at
    all" apart from "this database's migrations failed."
    """


@dataclasses.dataclass(frozen=True)
class Migration:
    version: int
    name: str
    path: pathlib.Path

    @property
    def is_python(self) -> bool:
        return self.path.suffix == ".py"


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _ensure_wal(con: sqlite3.Connection) -> None:
    """Switch a connection's database into WAL mode, racing safely.

    Read journal_mode first and only attempt the switch when it isn't
    already "wal". WAL is recorded in the file header and persists across
    connections and processes, so once one connection has switched a file,
    every later connection — including concurrent ones — takes this cheap
    read-only path and never touches the exclusive-lock code below at all.
    That collapses the unsafe window down to a brand-new file's very first
    connections, which is also why the bounded retry only has to survive a
    handful of racing first-connections, not ongoing traffic.

    The switch itself needs a retry because the FIRST switch of a database
    into WAL mode requires exclusive access to rewrite the file header and
    set up the wal-index, and — measured directly, not assumed — SQLite does
    NOT route that specific contention through the busy handler the way it
    does an ordinary write-lock wait: two threads racing plain BEGIN
    IMMEDIATE on an already-WAL database correctly waited the full 5.007s
    busy_timeout before one raised, but two threads racing this switch on a
    brand-new file failed in ~0.5ms with no wait at all. So a busy_timeout
    PRAGMA cannot fix this path; only a caller-side retry can. Measured
    against a brand-new file with 4 concurrent threads: 17/100 runs raised
    sqlite3.OperationalError("database is locked") with no retry, 0/100
    failed once the file already existed in WAL mode.

    Bounded, and the final failure is left to propagate rather than being
    swallowed or wrapped — a database that still can't reach WAL mode after
    a handful of short waits is a real problem the caller needs to see.

    The leading read below is deliberately OUTSIDE the retry guard. It only
    needs a SHARED lock — the same as any ordinary SELECT — because it just
    reports the pager's current mode without rewriting anything; it never
    attempts the file-header rewrite that requires the EXCLUSIVE lock, which
    is the operation this whole function exists to protect. Any number of
    connections can hold a SHARED lock at once, so two threads reading this
    concurrently cannot conflict with each other, and a thread reading while
    another holds the EXCLUSIVE lock for the switch just blocks briefly under
    the normal (busy_timeout-covered) path rather than hitting the unretried
    one. This is not assumed: isolating the read from the switch and racing
    each independently (4 and 8 concurrent threads, 300 attempts each, so
    1,200 and 2,400 read calls respectively) produced 0 read failures out of
    3,600 total read calls, against 35 and 19 switch failures in the same
    two runs. If a future SQLite version changes this, the fix is to move
    the read inside the loop below, not to add a second guard around it.
    """
    if con.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal":
        return
    for attempt in range(_WAL_SWITCH_ATTEMPTS):
        try:
            con.execute("PRAGMA journal_mode=WAL")
            return
        except sqlite3.OperationalError:
            if attempt == _WAL_SWITCH_ATTEMPTS - 1:
                raise
            time.sleep(_WAL_SWITCH_BACKOFF_SECS * (attempt + 1))


def connect(db_path) -> sqlite3.Connection:
    """A connection configured the way every Tubematic process expects one.

    WAL because three services write concurrently; foreign_keys because the
    schema relies on ON DELETE CASCADE (comments, video_metrics).
    """
    path = pathlib.Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # isolation_level=None turns off the driver's implicit transaction handling
    # so migrate() can issue BEGIN IMMEDIATE itself and hold it across the whole
    # run. With the default, the driver opens its own transaction before the
    # first DML and the explicit BEGIN either errors or nests unpredictably.
    con = sqlite3.connect(str(path), isolation_level=None)
    _ensure_wal(con)
    con.execute("PRAGMA foreign_keys=ON")
    return con


def discover(migrations_dir=None) -> list:
    """Every migration on disk, ascending by version.

    Anything not matching NNNN_<name>.(sql|py) is ignored rather than rejected —
    the directory legitimately holds __init__.py, and editor droppings must not
    become migrations. A duplicate version number IS rejected: two files
    claiming the same number means one of them silently never runs.
    """
    d = pathlib.Path(migrations_dir) if migrations_dir else MIGRATIONS_DIR
    found = {}
    for entry in sorted(d.iterdir()):
        if not entry.is_file():
            continue
        m = _FILENAME.match(entry.name)
        if not m:
            continue
        version = int(m.group(1))
        if version in found:
            raise MigrationError(
                f"duplicate migration version {version}: "
                f"{found[version].path.name} and {entry.name}"
            )
        found[version] = Migration(version=version, name=m.group(2), path=entry)
    return [found[v] for v in sorted(found)]


def _ensure_tracking_table(con: sqlite3.Connection) -> None:
    con.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version    INTEGER PRIMARY KEY,
            name       TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
    """)


def _applied_versions(con: sqlite3.Connection) -> set:
    _ensure_tracking_table(con)
    return {r[0] for r in con.execute("SELECT version FROM schema_migrations")}


def current_schema_version(db_path) -> int:
    """The highest applied migration, or 0 for a database that has none.

    0 covers both a brand-new file and a pre-migration database, which is
    correct: both need every migration, and 0001 is written to converge either.
    """
    path = pathlib.Path(db_path)
    if not path.exists():
        return 0
    con = sqlite3.connect(str(path))
    try:
        row = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        if not row:
            return 0
        return con.execute(
            "SELECT COALESCE(MAX(version), 0) FROM schema_migrations"
        ).fetchone()[0]
    finally:
        con.close()


# ── Backups ──────────────────────────────────────────────────────────────────

# Bound on the collision-suffix retry loop in backup_db — a pathological
# directory (or a bug generating the same stamp forever) must not spin it
# indefinitely.
_BACKUP_NAME_ATTEMPTS = 1000


def backup_dir_for(db_path) -> pathlib.Path:
    """Where backups go, derived rather than configured.

    The sibling `backups/` of the database's parent directory. In the container
    /data/tubematic.db yields /backups, which docker-compose.yml binds to
    ~/.tubematic-data/backups; on the host the same rule on
    ~/.tubematic-data/data/tubematic.db yields ~/.tubematic-data/backups. One
    rule, both contexts, nothing to set wrong.

    TUBEMATIC_BACKUPS_DIR overrides it, for tests.
    """
    env = os.environ.get("TUBEMATIC_BACKUPS_DIR", "").strip()
    if env:
        return pathlib.Path(env)
    return pathlib.Path(db_path).resolve().parent.parent / "backups"


def _backup_stamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def backup_db(db_path) -> pathlib.Path:
    """Copy the database aside. Returns the path written.

    Uses sqlite3's online backup API, never shutil.copy. The database runs in
    WAL mode with three concurrent writers, and a file copy taken while any of
    them holds a transaction produces a torn file — one that looks fine until
    the day it is restored. The online API takes a consistent snapshot of the
    last committed state instead.

    Never overwrites: the stamp has one-second resolution and a restart loop can
    reach here twice inside one second, so a collision appends a counter rather
    than discarding the earlier copy. The name is reserved with
    os.O_CREAT | os.O_EXCL, not a check-then-act exists() loop: two processes
    racing within the same stamp must land on genuinely different files, not
    both observe the same name as free and open it.

    The written file's permissions are set to match the source database's,
    never left at sqlite3's own default. Since TMDEV-73 the database is a
    credential store — API keys and the Discord webhook live in its settings
    table — and renderer/entrypoint.sh deliberately keeps it at 0660 with the
    host group for that reason. A backup must never be a more permissive copy
    of the same secrets than the file it was copied from. The os.open() mode
    (0o600) is deliberately more restrictive still, as a placeholder — it is
    always overwritten by the chmod below once the real content lands.

    A backup that fails partway is unlinked rather than left behind: a
    correctly-named, partially-written .db file in the backups directory is
    indistinguishable from a good one until someone tries to restore it.
    Because the name is reserved by this process via O_EXCL (not merely
    observed absent moments earlier), that unlink can only ever remove a file
    this call itself created — never a backup another concurrent caller holds.
    """
    src = pathlib.Path(db_path)
    if not src.exists():
        raise MigrationError(f"cannot back up {src}: it does not exist")

    from tubematic_core.version import version as _version

    out_dir = backup_dir_for(src)
    base = f"tubematic-before-v{_version()}-{_backup_stamp()}"
    out = None
    try:
        out_dir.mkdir(parents=True, exist_ok=True)

        candidate = out_dir / f"{base}.db"
        counter = 1
        fd = None
        while fd is None:
            try:
                fd = os.open(str(candidate), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            except FileExistsError:
                if counter > _BACKUP_NAME_ATTEMPTS:
                    raise MigrationError(
                        f"could not reserve a backup filename under {out_dir} "
                        f"after {_BACKUP_NAME_ATTEMPTS} attempts"
                    )
                candidate = out_dir / f"{base}-{counter}.db"
                counter += 1
        os.close(fd)
        out = candidate

        source = sqlite3.connect(str(src))
        try:
            dest = sqlite3.connect(str(out))
            try:
                source.backup(dest)
            finally:
                dest.close()
        finally:
            source.close()
        os.chmod(out, stat.S_IMODE(src.stat().st_mode))
    except MigrationError:
        raise
    except Exception as e:
        if out is not None and out.exists():
            out.unlink()
        raise MigrationError(f"database backup failed: {e}") from e
    return out


# ── Running migrations ───────────────────────────────────────────────────────

@dataclasses.dataclass(frozen=True)
class MigrationResult:
    applied: list
    from_version: int
    to_version: int
    backup_path: pathlib.Path | None


def _load_python_migration(mig: Migration):
    spec = importlib.util.spec_from_file_location(
        f"tubematic_core.migrations.{mig.path.stem}", mig.path)
    if spec is None or spec.loader is None:
        raise MigrationError(f"could not load migration {mig.path.name}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if not hasattr(module, "up"):
        raise MigrationError(f"{mig.path.name} defines no up(con) function")
    return module


def _split_statements(script: str) -> list:
    """Split a .sql migration into individual statements.

    sqlite3.complete_statement is the helper the sqlite3 REPL itself uses, so a
    semicolon inside a string literal does not split a statement.

    Needed because executescript() issues its own COMMIT and therefore cannot
    run inside the run-wide transaction below. Using it would silently drop the
    write lock that makes concurrent migrate() calls safe.
    """
    statements, buf = [], ""
    for line in script.splitlines(keepends=True):
        buf += line
        if sqlite3.complete_statement(buf):
            if buf.strip():
                statements.append(buf)
            buf = ""
    if buf.strip():
        statements.append(buf)
    return statements


def _apply_one(con: sqlite3.Connection, mig: Migration) -> None:
    """Apply one migration and stamp it. The CALLER owns the transaction.

    No commit here: the whole run is one transaction (see migrate), which is
    what stops two processes both applying the same migration. A migration is
    therefore never stamped unless it applied, and never applied without being
    stamped.
    """
    if mig.is_python:
        _load_python_migration(mig).up(con)
    else:
        for statement in _split_statements(mig.path.read_text()):
            con.execute(statement)
    con.execute(
        "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
        (mig.version, mig.name, _now()))


def migrate(db_path, *, backup: bool = True, migrations_dir=None) -> MigrationResult:
    """Bring `db_path` up to the latest migration. Idempotent.

    Called by every process rather than by one owner. A run with nothing pending
    costs one SELECT; a run with something pending holds a write lock from the
    first statement to the last, so a second process blocks, then finds nothing
    pending once the first commits.

    The whole run is ONE transaction, not one per migration. Those two cannot
    both hold in SQLite — a commit releases the lock — and the lock is what makes
    every-process-migrates safe, so the lock wins. Run-wide atomicity is also
    strictly stronger for the property that matters: a partially-migrated
    database is impossible.

    A backup is taken first, and only when something is pending AND a database
    already exists: a no-op start must not grow the backup directory, and a
    brand-new file has nothing to lose. If the backup fails the migration does
    not run.
    """
    path = pathlib.Path(db_path)
    existed = path.exists()
    con = connect(path)
    try:
        _ensure_tracking_table(con)
        found = discover(migrations_dir)
        applied = _applied_versions(con)
        from_version = max(applied) if applied else 0

        if not [m for m in found if m.version not in applied]:
            return MigrationResult([], from_version, from_version, None)

        backup_path = None
        if backup and existed:
            # Deliberately taken before the lock below, not inside it. Two
            # containers starting together can both see something pending and
            # each write a backup before either wins the BEGIN IMMEDIATE —
            # observed live as two files sharing a timestamp, the second
            # carrying the collision suffix. Benign (a spare copy, never
            # corruption), and moving this inside the lock would make every
            # no-op start pay for the lock just to avoid it.
            backup_path = backup_db(path)

        # One transaction for the whole run. Anyone else arriving now blocks
        # here rather than re-applying what this run is part-way through.
        con.execute("BEGIN IMMEDIATE")
        try:
            applied = _applied_versions(con)
            done = []
            for mig in [m for m in found if m.version not in applied]:
                _apply_one(con, mig)
                done.append(mig.version)
            con.commit()
        except MigrationError:
            con.rollback()
            raise
        except Exception as e:
            con.rollback()
            raise MigrationError(f"migration failed: {e}") from e

        to_version = max(applied | set(done)) if (applied or done) else 0
        return MigrationResult(done, from_version, to_version, backup_path)
    finally:
        con.close()


def assert_schema_current(db_path, *, migrations_dir=None) -> None:
    """Raise if `db_path` has migrations it has not applied.

    Not used by the services — they all call migrate(). This is for host-side
    tools that should report a stale database rather than silently change one.
    """
    current = current_schema_version(db_path)
    pending = [m.version for m in discover(migrations_dir) if m.version > current]
    if pending:
        raise MigrationError(
            f"database schema is behind: at {current:04d}, "
            f"pending {', '.join(f'{v:04d}' for v in pending)}. "
            f"Run scripts/migrate_db.py, or start tubematic-api, "
            f"tubematic-renderer or tubematic-mcp — any of them calls "
            f"migrate() on startup.")
