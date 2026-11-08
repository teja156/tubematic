"""The 0018 migration: the mascots and mascot_versions tables, the three new
columns, and the seeded Tubi row.

Upgrading must change nothing for an existing install: every existing project
and video gets '' / 0 (no mascot), and the only new rows are the shipped
mascot. Tubi's drawing code is not in the database (it is a versioned repo
file), so its version row carries an empty code.
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


def _db_at_0017(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_to_0017"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 17:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO projects (id, name, created_at) VALUES ('p1', 'P', 'x')")
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('v1', 't', 'VOICE_READY', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    return db


def test_existing_projects_and_videos_get_no_mascot(tmp_path):
    db = _db_at_0017(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT default_mascot_id FROM projects").fetchall() == [("",)]
    assert con.execute("SELECT mascot_id, mascot_version FROM videos").fetchall() == [("", 0)]
    con.close()


def test_tubi_is_seeded_ready_at_version_one_with_no_code_in_the_db(tmp_path):
    db = _db_at_0017(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    row = con.execute("SELECT id, name, builtin, status, approved_version, archived FROM mascots").fetchall()
    assert row == [("tubi", "Tubi", 1, "READY", 1, 0)]
    ver = con.execute("SELECT mascot_id, version, code, approved_at FROM mascot_versions").fetchall()
    assert len(ver) == 1 and ver[0][:3] == ("tubi", 1, "") and ver[0][3] != ""
    con.close()


def test_a_second_migrate_is_a_no_op(tmp_path):
    db = _db_at_0017(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("UPDATE mascots SET name = 'Renamed' WHERE id = 'tubi'")
    con.commit()
    con.close()
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT name FROM mascots").fetchall() == [("Renamed",)]
    assert con.execute("SELECT COUNT(*) FROM mascot_versions").fetchone() == (1,)
    con.close()


def test_a_new_mascot_row_defaults_to_pending_and_unapproved(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO mascots (id, name) VALUES ('moss', 'Moss')")
    assert con.execute("SELECT status, approved_version, builtin, archived, attempt_count FROM mascots "
                       "WHERE id = 'moss'").fetchone() == ("PENDING", 0, 0, 0, 0)
    con.close()
