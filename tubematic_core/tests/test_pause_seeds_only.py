"""The 0004 pause-seeds-only migration (TMDEV-115).

Pause now exists only on curriculum seeds, and nothing in the dashboard offers
a control for a non-seed domain's status. A paused non-seed row left behind by
an older install would therefore stay paused forever with no way to change it,
so the migration activates every one of them — and must leave a paused SEED
alone, because that pause is still meaningful and still controllable.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_at_0003_with_projects(tmp_path):
    """A database migrated only as far as 0003, holding one row of each kind."""
    older = tmp_path / "migrations_to_0003"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 3:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.executemany(
        "INSERT INTO projects (id, name, is_curriculum_seed, status, created_at) "
        "VALUES (?, ?, ?, ?, '2026-01-01T00:00:00Z')",
        [("paused-seed", "Paused seed", 1, "paused"),
         ("paused-nonseed", "Paused non-seed", 0, "paused"),
         ("active-nonseed", "Active non-seed", 0, "active"),
         ("active-seed", "Active seed", 1, "active")],
    )
    con.commit()
    con.close()
    return db


def _statuses(db):
    con = sqlite3.connect(db)
    out = dict(con.execute("SELECT id, status FROM projects"))
    con.close()
    return out


def test_a_paused_non_seed_becomes_active(tmp_path):
    db = _db_at_0003_with_projects(tmp_path)
    tdb.migrate(db)
    assert _statuses(db)["paused-nonseed"] == "active"


def test_a_paused_seed_stays_paused(tmp_path):
    """The half that is easy to over-reach on: a blanket UPDATE would unpause
    a seed the human paused on purpose."""
    db = _db_at_0003_with_projects(tmp_path)
    tdb.migrate(db)
    assert _statuses(db)["paused-seed"] == "paused"


def test_active_rows_are_untouched(tmp_path):
    db = _db_at_0003_with_projects(tmp_path)
    tdb.migrate(db)
    s = _statuses(db)
    assert s["active-nonseed"] == "active"
    assert s["active-seed"] == "active"


def test_no_paused_non_seed_survives(tmp_path):
    db = _db_at_0003_with_projects(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    n = con.execute(
        "SELECT COUNT(*) FROM projects WHERE status = 'paused' AND is_curriculum_seed = 0"
    ).fetchone()[0]
    con.close()
    assert n == 0


def test_the_migration_is_recorded(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    assert tdb.current_schema_version(db) >= 4
