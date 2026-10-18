"""The migration runner (TMDEV-91)."""
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402


@pytest.fixture
def migdir(tmp_path):
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "__init__.py").write_text("")
    return d


def _sql(migdir, name, body="CREATE TABLE IF NOT EXISTS t_%s (id INTEGER);"):
    if "%s" in body:
        body = body % name.split("_", 1)[1].replace(".sql", "")
    (migdir / name).write_text(body)


def test_discover_sorts_by_numeric_prefix_not_string(migdir):
    """0002 must precede 0010. A string sort gets this right only by accident of
    zero-padding, and a 5-digit migration would break it silently."""
    for n in ("0010_ten.sql", "0002_two.sql", "0001_one.sql"):
        _sql(migdir, n)
    assert [m.version for m in tdb.discover(migdir)] == [1, 2, 10]


def test_discover_reads_the_name(migdir):
    _sql(migdir, "0007_add_widgets.sql")
    assert tdb.discover(migdir)[0].name == "add_widgets"


def test_discover_accepts_both_py_and_sql(migdir):
    _sql(migdir, "0001_one.sql")
    (migdir / "0002_two.py").write_text("def up(con):\n    pass\n")
    assert [m.version for m in tdb.discover(migdir)] == [1, 2]


def test_discover_allows_gaps(migdir):
    """A reverted migration must not force its successors to renumber."""
    _sql(migdir, "0001_one.sql")
    _sql(migdir, "0003_three.sql")
    assert [m.version for m in tdb.discover(migdir)] == [1, 3]


def test_duplicate_versions_are_a_hard_error(migdir):
    _sql(migdir, "0001_one.sql")
    _sql(migdir, "0001_other.sql")
    with pytest.raises(tdb.MigrationError, match="duplicate"):
        tdb.discover(migdir)


def test_unparseable_filenames_are_ignored(migdir):
    """__init__.py, README.md and editor droppings must not become migrations."""
    _sql(migdir, "0001_one.sql")
    (migdir / "README.md").write_text("notes")
    (migdir / "notes.txt").write_text("x")
    (migdir / ".0002_hidden.sql").write_text("")
    assert [m.version for m in tdb.discover(migdir)] == [1]


def test_current_schema_version_is_zero_on_an_untracked_db(tmp_path):
    db = tmp_path / "x.db"
    sqlite3.connect(db).close()
    assert tdb.current_schema_version(db) == 0


def test_current_schema_version_is_zero_on_a_missing_file(tmp_path):
    assert tdb.current_schema_version(tmp_path / "nope.db") == 0


def test_ensure_tracking_table_is_idempotent(tmp_path):
    db = tmp_path / "x.db"
    con = tdb.connect(db)
    tdb._ensure_tracking_table(con)
    tdb._ensure_tracking_table(con)
    cols = [r[1] for r in con.execute("PRAGMA table_info(schema_migrations)")]
    con.close()
    assert cols == ["version", "name", "applied_at"]


def test_connect_enables_wal_and_foreign_keys(tmp_path):
    con = tdb.connect(tmp_path / "x.db")
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert con.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    con.close()


def test_connect_creates_the_parent_directory(tmp_path):
    con = tdb.connect(tmp_path / "deep" / "nested" / "x.db")
    con.close()
    assert (tmp_path / "deep" / "nested" / "x.db").exists()


def test_concurrent_connect_against_a_new_file_does_not_race(tmp_path):
    """Regression pin for the WAL-switch race fixed in _ensure_wal.

    Measured directly (see db.py's _ensure_wal docstring): 4 threads racing
    PRAGMA journal_mode=WAL on a brand-new file failed ~17/100 times with no
    retry. A single race here would therefore only catch a reintroduced bug
    at that rate ~17% of the time — worse than a coin flip. REPEAT_COUNT=30
    independent races drops the odds of a 17%-rate regression slipping through
    by luck to about 0.83**30 =~ 0.4%, while still running in well under a
    second since each race is just four connect() calls against an empty file.
    """
    import threading

    REPEAT_COUNT = 30
    for i in range(REPEAT_COUNT):
        db = tmp_path / f"race-{i}.db"
        errors = []

        def run():
            try:
                tdb.connect(db).close()
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (i, errors)
        con = sqlite3.connect(db)
        mode = con.execute("PRAGMA journal_mode").fetchone()[0]
        con.close()
        assert mode.lower() == "wal", (i, mode)


def test_the_real_migrations_directory_discovers_cleanly():
    """Guards the shipped tree: duplicate or malformed filenames fail here."""
    found = tdb.discover()
    assert [m.version for m in found] == sorted(m.version for m in found)
    assert found, "no migrations found in the shipped migrations directory"


# ── migrate() ────────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def test_migrate_applies_pending_and_stamps_them(tmp_path, migdir):
    _sql(migdir, "0001_one.sql")
    _sql(migdir, "0002_two.sql")
    db = tmp_path / "x.db"
    result = tdb.migrate(db, migrations_dir=migdir)

    assert result.applied == [1, 2]
    assert result.from_version == 0
    assert result.to_version == 2
    con = sqlite3.connect(db)
    rows = con.execute("SELECT version, name FROM schema_migrations ORDER BY version").fetchall()
    con.close()
    assert rows == [(1, "one"), (2, "two")]


def test_migrate_is_a_no_op_the_second_time(tmp_path, migdir):
    _sql(migdir, "0001_one.sql")
    db = tmp_path / "x.db"
    tdb.migrate(db, migrations_dir=migdir)
    again = tdb.migrate(db, migrations_dir=migdir)
    assert again.applied == []
    assert again.from_version == again.to_version == 1


def test_migrate_applies_only_what_is_missing(tmp_path, migdir):
    _sql(migdir, "0001_one.sql")
    db = tmp_path / "x.db"
    tdb.migrate(db, migrations_dir=migdir)
    _sql(migdir, "0002_two.sql")
    assert tdb.migrate(db, migrations_dir=migdir).applied == [2]


def test_migrate_runs_python_migrations(tmp_path, migdir):
    (migdir / "0001_py.py").write_text(
        "def up(con):\n    con.execute('CREATE TABLE made_by_python (id INTEGER)')\n"
    )
    db = tmp_path / "x.db"
    tdb.migrate(db, migrations_dir=migdir)
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT 1 FROM sqlite_master WHERE name='made_by_python'").fetchone()
    con.close()


def test_a_python_migration_without_up_is_an_error(tmp_path, migdir):
    (migdir / "0001_bad.py").write_text("x = 1\n")
    with pytest.raises(tdb.MigrationError, match="up"):
        tdb.migrate(tmp_path / "x.db", migrations_dir=migdir)


def test_a_failing_migration_is_not_stamped(tmp_path, migdir):
    """The worst available outcome is a half-applied migration recorded as done.
    A migration is never stamped unless it applied."""
    _sql(migdir, "0001_one.sql")
    (migdir / "0002_boom.sql").write_text(
        "CREATE TABLE fine (id INTEGER);\nSELECT this_function_does_not_exist();")
    db = tmp_path / "x.db"
    with pytest.raises(tdb.MigrationError):
        tdb.migrate(db, migrations_dir=migdir)
    con = sqlite3.connect(db)
    assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='fine'").fetchone()
    con.close()


def test_a_failing_migration_rolls_back_the_whole_run(tmp_path, migdir):
    """The run is one transaction, so a failure at 0002 also unwinds 0001.

    That is deliberate and is the cost of holding the write lock across the run
    — SQLite releases the lock on commit, so per-migration commits would let a
    second process apply a migration this one is part-way through. Run-wide
    atomicity is the stronger guarantee anyway: a partially-migrated database
    cannot exist."""
    _sql(migdir, "0001_one.sql")
    (migdir / "0002_boom.sql").write_text("SELECT nope();")
    db = tmp_path / "x.db"
    with pytest.raises(tdb.MigrationError):
        tdb.migrate(db, migrations_dir=migdir)
    assert tdb.current_schema_version(db) == 0
    con = sqlite3.connect(db)
    assert not con.execute("SELECT 1 FROM sqlite_master WHERE name='t_one'").fetchone()
    con.close()


def test_a_semicolon_inside_a_string_does_not_split_a_statement(tmp_path, migdir):
    """_split_statements replaces executescript, so it has to get this right."""
    (migdir / "0001_str.sql").write_text(
        "CREATE TABLE s (v TEXT);\n"
        "INSERT INTO s VALUES ('a;b');\n")
    db = tmp_path / "x.db"
    tdb.migrate(db, migrations_dir=migdir)
    con = sqlite3.connect(db)
    assert con.execute("SELECT v FROM s").fetchone()[0] == "a;b"
    con.close()


def test_backup_is_taken_when_something_is_pending(tmp_path, migdir):
    _sql(migdir, "0001_one.sql")
    db = tmp_path / "x.db"
    tdb.connect(db).close()
    result = tdb.migrate(db, migrations_dir=migdir)
    assert result.backup_path is not None
    assert result.backup_path.exists()


def test_no_backup_when_nothing_is_pending(tmp_path, migdir):
    """Otherwise every container restart grows the backup directory."""
    _sql(migdir, "0001_one.sql")
    db = tmp_path / "x.db"
    tdb.connect(db).close()
    tdb.migrate(db, migrations_dir=migdir)
    before = list((tmp_path / "backups").iterdir())
    result = tdb.migrate(db, migrations_dir=migdir)
    assert result.backup_path is None
    assert list((tmp_path / "backups").iterdir()) == before


def test_no_backup_for_a_brand_new_database(tmp_path, migdir):
    """There is nothing to lose, and a backup of an empty file is noise."""
    _sql(migdir, "0001_one.sql")
    result = tdb.migrate(tmp_path / "brand-new.db", migrations_dir=migdir)
    assert result.backup_path is None
    assert result.applied == [1]


def test_backup_failure_fails_closed(tmp_path, migdir, monkeypatch):
    """No backup, no migration. The database must be untouched afterwards."""
    _sql(migdir, "0001_one.sql")
    db = tmp_path / "x.db"
    tdb.connect(db).close()
    monkeypatch.setattr(tdb, "backup_db", lambda p: (_ for _ in ()).throw(
        tdb.MigrationError("disk full")))
    with pytest.raises(tdb.MigrationError, match="disk full"):
        tdb.migrate(db, migrations_dir=migdir)
    assert tdb.current_schema_version(db) == 0


def test_allow_no_backup_skips_it(tmp_path, migdir):
    _sql(migdir, "0001_one.sql")
    db = tmp_path / "x.db"
    tdb.connect(db).close()
    result = tdb.migrate(db, migrations_dir=migdir, backup=False)
    assert result.backup_path is None
    assert result.applied == [1]


def test_concurrent_migrate_applies_once(tmp_path, migdir):
    """Every process calls migrate(). Two starting together must not both apply
    0001 — the lock is what makes that safe."""
    import threading
    _sql(migdir, "0001_one.sql")
    db = tmp_path / "x.db"
    results, errors = [], []

    def run():
        try:
            results.append(tdb.migrate(db, migrations_dir=migdir))
        except Exception as e:  # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=run) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, errors
    assert sum(len(r.applied) for r in results) == 1
    assert tdb.current_schema_version(db) == 1


def _copy_of_the_real_baseline(migdir):
    """Copies the shipped 0001_baseline.py verbatim rather than reimplementing
    its bug shape in a synthetic fixture. Every concurrency/atomicity test
    above uses a .sql fixture, which routes through _split_statements and so
    can never exercise a .py migration calling con.executescript() itself —
    which is exactly what 0001_baseline.py used to do. Using a synthetic .py
    migration that hardcodes executescript() would stay red forever regardless
    of whether 0001_baseline.py is fixed; copying the real file means these
    tests track whatever it actually does."""
    real = REPO_ROOT / "tubematic_core" / "migrations" / "0001_baseline.py"
    (migdir / "0001_baseline.py").write_text(real.read_text())


def test_concurrent_migrate_against_the_real_py_migration_applies_once(tmp_path, migdir):
    """Regression pin for the executescript() bug in 0001_baseline.py.

    executescript() issues an implicit COMMIT before running, which released
    migrate()'s run-wide BEGIN IMMEDIATE at the first statement of the only
    migration that ships. A second process blocked on BEGIN IMMEDIATE then
    unblocked mid-migration, re-read a still-unstamped schema_migrations, and
    raced to re-apply — the loser failing on a duplicate stamp. The race
    window is small (the gap between executescript()'s implicit COMMIT and
    the rest of up() finishing), so — same reasoning as
    test_concurrent_connect_against_a_new_file_does_not_race — one race is not
    enough to trust; REPEAT_COUNT independent races is. Fails against the
    buggy baseline (reliably, across repeats); passes once 0001_baseline.py
    stops using executescript().
    """
    import threading

    REPEAT_COUNT = 20
    for i in range(REPEAT_COUNT):
        d = migdir / str(i)
        d.mkdir()
        _copy_of_the_real_baseline(d)
        db = tmp_path / f"race-{i}.db"
        results, errors = [], []

        def run():
            try:
                results.append(tdb.migrate(db, migrations_dir=d))
            except Exception as e:  # noqa: BLE001
                errors.append(e)

        threads = [threading.Thread(target=run) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors, (i, errors)
        assert sum(len(r.applied) for r in results) == 1, (i, results)
        assert tdb.current_schema_version(db) == 1, i


def test_a_failing_py_migration_after_the_real_baseline_leaves_nothing_applied(tmp_path, migdir):
    """The atomicity half of the same bug: 0001_baseline.py's executescript()
    call committed its CREATE TABLEs (and its own schema_migrations stamp)
    immediately, so a later migration's failure could no longer unwind it —
    0001 was already durable. This must genuinely distinguish autocommit
    behaviour from run-wide atomicity, not just check that migrate() raised:
    against the buggy baseline, current_schema_version comes back 1 and
    'videos' already exists even though the overall run raised. Only after
    the fix does the single run-wide transaction unwind 0001 along with the
    failing 0002.
    """
    _copy_of_the_real_baseline(migdir)
    (migdir / "0002_boom.py").write_text(
        "def up(con):\n    raise RuntimeError('boom')\n")
    db = tmp_path / "x.db"

    with pytest.raises(tdb.MigrationError):
        tdb.migrate(db, migrations_dir=migdir)

    assert tdb.current_schema_version(db) == 0
    con = sqlite3.connect(db)
    try:
        assert not con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='videos'"
        ).fetchone()
    finally:
        con.close()


def test_assert_schema_current_passes_on_a_migrated_db(tmp_path, migdir):
    _sql(migdir, "0001_one.sql")
    db = tmp_path / "x.db"
    tdb.migrate(db, migrations_dir=migdir)
    tdb.assert_schema_current(db, migrations_dir=migdir)


def test_assert_schema_current_raises_when_behind(tmp_path, migdir):
    _sql(migdir, "0001_one.sql")
    db = tmp_path / "x.db"
    tdb.migrate(db, migrations_dir=migdir)
    _sql(migdir, "0002_two.sql")
    with pytest.raises(tdb.MigrationError, match="0002|behind|pending"):
        tdb.assert_schema_current(db, migrations_dir=migdir)
