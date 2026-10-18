"""The 0010 default-script-profile migration (TMDEV-145).

Every existing domain must come out with no default profile: a non-blank
default would start writing a domain's curriculum videos in a style nobody
picked for it.
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


def test_a_fresh_database_gets_the_column(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    con = sqlite3.connect(db)
    cols = {r[1] for r in con.execute("PRAGMA table_info(projects)")}
    con.close()
    assert "default_script_profile_id" in cols


def test_existing_domains_get_no_default_profile(tmp_path):
    older = tmp_path / "migrations_to_0009"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 9:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO projects (id, name, is_curriculum_seed, status, created_at) "
                "VALUES ('p1', 'Domain', 1, 'active', '2026-01-01')")
    con.commit()
    con.close()

    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op

    con = sqlite3.connect(db)
    row = con.execute("SELECT default_script_profile_id FROM projects "
                      "WHERE id = 'p1'").fetchone()
    con.close()
    assert row == ("",)
