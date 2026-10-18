"""Pre-migration database backups (TMDEV-91)."""
import os
import pathlib
import sqlite3
import stat
import sys
import threading

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402


@pytest.fixture(autouse=True)
def _no_env_override(monkeypatch):
    monkeypatch.delenv("TUBEMATIC_BACKUPS_DIR", raising=False)


def _seeded(path):
    con = tdb.connect(path)
    con.execute("CREATE TABLE t (id INTEGER, payload TEXT)")
    con.executemany("INSERT INTO t VALUES (?, ?)", [(i, f"row-{i}") for i in range(500)])
    con.commit()
    return con


def test_backup_dir_is_the_sibling_of_the_db_parent(tmp_path):
    """One rule that lands correctly in both contexts:
        /data/tubematic.db                      -> /backups
        ~/.tubematic-data/data/tubematic.db     -> ~/.tubematic-data/backups
    """
    assert tdb.backup_dir_for("/data/tubematic.db") == pathlib.Path("/backups")
    root = tmp_path / ".tubematic-data"
    assert tdb.backup_dir_for(root / "data" / "tubematic.db") == root / "backups"


def test_env_override_wins(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "elsewhere"))
    assert tdb.backup_dir_for("/data/tubematic.db") == tmp_path / "elsewhere"


def test_backup_filename_carries_version_and_timestamp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_VERSION", "1.2.3")
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()
    out = tdb.backup_db(db)
    assert out.name.startswith("tubematic-before-v1.2.3-")
    assert out.suffix == ".db"


def test_backup_contains_every_row(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()
    out = tdb.backup_db(db)
    con = sqlite3.connect(out)
    assert con.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 500
    con.close()


def test_backup_is_consistent_while_a_writer_holds_the_database(tmp_path):
    """The reason this uses sqlite3's online backup API and not shutil.copy.

    Under WAL a plain file copy taken mid-transaction yields a torn file that
    looks fine until someone restores it. Here a second connection holds an open
    write transaction throughout the backup; the result must still be a readable
    database showing the last committed state.
    """
    db = tmp_path / "data" / "tubematic.db"
    writer = _seeded(db)
    writer.execute("BEGIN IMMEDIATE")
    writer.execute("INSERT INTO t VALUES (9999, 'uncommitted')")
    out = tdb.backup_db(db)
    writer.rollback()
    writer.close()

    con = sqlite3.connect(out)
    assert con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert con.execute("SELECT COUNT(*) FROM t WHERE id = 9999").fetchone()[0] == 0
    assert con.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 500
    con.close()


def test_two_backups_in_the_same_second_do_not_overwrite(tmp_path, monkeypatch):
    """The timestamp has one-second resolution; a container restart loop can
    call this twice inside one second, and losing the first copy would defeat
    the entire point of taking it."""
    monkeypatch.setattr(tdb, "_backup_stamp", lambda: "20260912-120000")
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()
    first = tdb.backup_db(db)
    second = tdb.backup_db(db)
    assert first != second
    assert first.exists() and second.exists()


def _patched_exists_synced_on_barrier(barrier, real_exists):
    """A stand-in for pathlib.Path.exists that reproduces the exact race
    reported live: two concurrent callers each check whether a candidate
    backup filename is taken, both see "no", and only then does either
    create it. A bare thread race would only reproduce this on scheduler
    luck; blocking every "not yet taken" answer on a 2-party barrier forces
    both callers to observe "absent" before either can act on it, every
    single run.

    Only intercepts checks on backup-shaped filenames (the
    "tubematic-before-v..." prefix) — src's own existence check, and
    anything else pathlib touches along the way, get the real answer
    untouched.
    """
    def _exists(self):
        if self.name.startswith("tubematic-before-v"):
            result = real_exists(self)
            if not result:
                barrier.wait(timeout=5)
            return result
        return real_exists(self)
    return _exists


def test_two_concurrent_backups_in_the_same_stamp_land_on_different_files(
        tmp_path, monkeypatch):
    """The destructive bug's non-destructive half: two callers racing to back
    up within the same one-second stamp must reserve genuinely different
    filenames. A check-then-act exists() loop lets both observe a name as
    free and both open it — this was observed live (two containers starting
    together produced two snapshots inside one second), not merely a
    hypothetical timing window."""
    monkeypatch.setattr(tdb, "_backup_stamp", lambda: "20260912-120000")
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()

    barrier = threading.Barrier(2)
    monkeypatch.setattr(
        pathlib.Path, "exists",
        _patched_exists_synced_on_barrier(barrier, pathlib.Path.exists))

    results = []
    errors = []

    def _run():
        try:
            results.append(tdb.backup_db(db))
        except Exception as e:  # noqa: BLE001 - captured for the assertion below
            errors.append(e)

    threads = [threading.Thread(target=_run) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not errors, f"concurrent backup raised: {errors}"
    assert len(results) == 2
    assert results[0] != results[1], (
        "two concurrent callers reserved the same backup filename")
    assert os.path.isfile(results[0]) and os.path.isfile(results[1])


def test_a_failed_concurrent_backup_does_not_delete_a_winners_backup(
        tmp_path, monkeypatch):
    """The destructive half: if a second, losing caller's failure cleanup
    ever runs against a name a first, winning caller already wrote — exactly
    the collision the previous test forces — the loser's unlink must not be
    able to remove the winner's completed, valid backup. Before the fix, the
    reservation loop's check-then-act race hands both callers the identical
    path; the loser's own cleanup then deletes what the winner just wrote,
    while the winner believes it has a good backup on disk."""
    monkeypatch.setattr(tdb, "_backup_stamp", lambda: "20260912-120000")
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()

    barrier = threading.Barrier(2)
    monkeypatch.setattr(
        pathlib.Path, "exists",
        _patched_exists_synced_on_barrier(barrier, pathlib.Path.exists))

    winner_done = threading.Event()
    real_connect = sqlite3.connect

    class _FailingSource:
        def __init__(self, real):
            self._real = real

        def backup(self, *a, **kw):
            raise sqlite3.OperationalError("disk full")

        def close(self):
            self._real.close()

    def _connect(path, *a, **kw):
        # Only the loser's connection to the SOURCE database (the first
        # sqlite3.connect() call backup_db makes) is broken, and only after
        # the winner has fully finished writing and closed its own backup —
        # so a real, complete file is sitting at the shared name when the
        # loser's cleanup runs.
        if threading.current_thread().name == "loser" and path == str(db):
            winner_done.wait(timeout=10)
            return _FailingSource(real_connect(path, *a, **kw))
        return real_connect(path, *a, **kw)

    monkeypatch.setattr(tdb.sqlite3, "connect", _connect)

    results = {}

    def _winner():
        results["winner"] = tdb.backup_db(db)
        winner_done.set()

    def _loser():
        try:
            tdb.backup_db(db)
        except tdb.MigrationError as e:
            results["loser_error"] = e

    t1 = threading.Thread(target=_winner, name="winner")
    t2 = threading.Thread(target=_loser, name="loser")
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert "winner" in results, "winner thread did not complete"
    assert "loser_error" in results, "loser thread did not fail as expected"
    # os.path.isfile, not Path.exists() -- the latter is still patched here
    # and would itself re-enter the barrier on a "file is gone" answer.
    assert os.path.isfile(results["winner"]), (
        "the losing caller's failure cleanup deleted the winning caller's "
        "valid backup")


def test_backup_reservation_gives_up_after_too_many_collisions(tmp_path, monkeypatch):
    """The collision-suffix retry loop must have a bound: a pathological
    directory (or a bug producing the same stamp forever) must not spin it
    indefinitely."""
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()

    real_open = os.open

    def _always_taken(path, flags, *a, **kw):
        if flags & os.O_EXCL:
            raise FileExistsError(17, "File exists")
        return real_open(path, flags, *a, **kw)

    monkeypatch.setattr(tdb.os, "open", _always_taken)
    with pytest.raises(tdb.MigrationError, match="could not reserve"):
        tdb.backup_db(db)


def test_backup_creates_the_directory(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()
    assert not (tmp_path / "backups").exists()
    tdb.backup_db(db)
    assert (tmp_path / "backups").is_dir()


def test_backup_of_a_missing_database_raises(tmp_path):
    with pytest.raises(tdb.MigrationError, match="does not exist"):
        tdb.backup_db(tmp_path / "nope.db")


def test_backup_failure_raises_migration_error(tmp_path, monkeypatch):
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()
    monkeypatch.setattr(tdb, "backup_dir_for", lambda p: pathlib.Path("/proc/nope/backups"))
    with pytest.raises(tdb.MigrationError):
        tdb.backup_db(db)


def test_backup_permissions_match_the_source(tmp_path):
    """The database is a credential store (API keys, the Discord webhook live
    in settings) and renderer/entrypoint.sh deliberately tightens it to 0660 +
    the host group. A backup left at sqlite3's own default (0644, root-owned
    in a container) would be a more permissive copy of the same secrets."""
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()
    db.chmod(0o640)
    out = tdb.backup_db(db)
    assert stat.S_IMODE(out.stat().st_mode) == 0o640


def _break_the_backup_call(monkeypatch):
    """Makes source.backup(dest) raise inside backup_db, without touching
    sqlite3.Connection itself (a C type — its methods can't be monkeypatched
    directly). Wraps only the FIRST sqlite3.connect() call backup_db makes
    (the source connection, the one .backup() is actually called on) in a
    proxy whose backup() raises and whose close() still closes the real
    connection; the second call (the dest connection) is left untouched so
    its file is created on disk exactly as in a real partial failure."""
    real_connect = sqlite3.connect
    calls = []

    class _FailingSource:
        def __init__(self, real):
            self._real = real

        def backup(self, *a, **kw):
            raise sqlite3.OperationalError("disk full")

        def close(self):
            self._real.close()

    def _connect(path, *a, **kw):
        con = real_connect(path, *a, **kw)
        calls.append(path)
        return _FailingSource(con) if len(calls) == 1 else con

    monkeypatch.setattr(tdb.sqlite3, "connect", _connect)


def test_a_failed_backup_removes_the_partial_file(tmp_path, monkeypatch):
    """A correctly-named, partially-written .db file left behind in the
    backups directory is indistinguishable from a good one until someone
    tries to restore it."""
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()
    _break_the_backup_call(monkeypatch)
    with pytest.raises(tdb.MigrationError):
        tdb.backup_db(db)
    assert list(tdb.backup_dir_for(db).iterdir()) == []


def test_a_failed_backup_does_not_delete_an_earlier_good_one(tmp_path, monkeypatch):
    db = tmp_path / "data" / "tubematic.db"
    _seeded(db).close()
    first = tdb.backup_db(db)
    _break_the_backup_call(monkeypatch)
    with pytest.raises(tdb.MigrationError):
        tdb.backup_db(db)
    assert first.exists()
