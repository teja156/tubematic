"""The 0013 domain topic-cap migration (TMDEV-153).

A domain whose count of topics reaches its cap is expired and takes no more
research topics. The migration must therefore never expire a domain that was
filing happily before the upgrade: one already at or past the default gets
headroom. Every video ever filed counts, archived and rejected ones included.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tubematic_core import db as tdb  # noqa: E402


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_at_0012_with(tmp_path, domains: dict[str, int]):
    """A database migrated to 0012 holding each domain with that many videos,
    a third of them archived and a third rejected."""
    older = tmp_path / "migrations_to_0012"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 12:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    for pid, n in domains.items():
        con.execute("INSERT INTO projects (id, name, is_curriculum_seed, status, created_at) "
                    "VALUES (?, ?, 1, 'active', '2026-01-01')", (pid, pid))
        for i in range(n):
            archived = "2026-02-01" if i % 3 == 0 else None
            status = "TOPIC_REJECTED" if i % 3 == 1 else "PUBLISHED"
            con.execute("INSERT INTO videos (id, topic, status, project_id, archived_at, "
                        "created_at, updated_at) VALUES (?, 't', ?, ?, ?, '2026-01-01', "
                        "'2026-01-01')", (f"{pid}-{i}", status, pid, archived))
    con.commit()
    con.close()
    return db


def _caps(db) -> dict[str, int]:
    con = sqlite3.connect(db)
    rows = dict(con.execute("SELECT id, topic_cap FROM projects").fetchall())
    con.close()
    return rows


def test_a_fresh_database_gets_the_column_and_the_index(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    con = sqlite3.connect(db)
    cols = {r[1]: r[4] for r in con.execute("PRAGMA table_info(projects)")}
    indexes = {r[1] for r in con.execute("PRAGMA index_list(videos)")}
    con.close()
    assert cols["topic_cap"] == "100"
    assert "idx_videos_project_id" in indexes


@pytest.mark.parametrize("videos,cap", [
    (0, 100),
    (30, 100),
    (99, 100),
    (100, 200),   # at the default it would expire on upgrade
    (120, 220),   # archived and rejected rows count
    (650, 750),
    (700, 750),   # never above the maximum
])
def test_a_domain_gets_headroom_over_what_it_already_holds(tmp_path, videos, cap):
    db = _db_at_0012_with(tmp_path, {"d": videos})
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    assert _caps(db) == {"d": cap}


def test_each_domain_is_counted_on_its_own(tmp_path):
    db = _db_at_0012_with(tmp_path, {"small": 10, "big": 150})
    tdb.migrate(db)
    assert _caps(db) == {"small": 100, "big": 250}
