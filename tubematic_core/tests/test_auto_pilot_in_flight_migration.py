"""The 0012 Auto Pilot in-progress limit migration (TMDEV-150).

auto_pilot_max_scheduled is renamed auto_pilot_max_in_flight. The stored
number carries over verbatim: the new count includes everything the old one
did, so the same number can only stop Auto Pilot sooner, never charge more.
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


def _db_at_0011_with(tmp_path, settings: dict) -> pathlib.Path:
    older = tmp_path / "migrations_to_0011"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 11:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", settings.items())
    con.commit()
    con.close()
    return db


def _settings(db) -> dict:
    con = sqlite3.connect(db)
    rows = dict(con.execute("SELECT key, value FROM settings").fetchall())
    con.close()
    return rows


@pytest.mark.parametrize("value", ["5", "0", "500"])
def test_the_stored_number_carries_over_verbatim(tmp_path, value):
    # 0 stays 0: an install that never set the ceiling keeps no limit.
    db = _db_at_0011_with(tmp_path, {"auto_pilot_max_scheduled": value})
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    settings = _settings(db)
    assert settings["auto_pilot_max_in_flight"] == value
    assert "auto_pilot_max_scheduled" not in settings


def test_an_install_that_never_stored_one_gets_no_row(tmp_path):
    db = _db_at_0011_with(tmp_path, {"auto_pilot_enabled": "true"})
    tdb.migrate(db)
    settings = _settings(db)
    assert "auto_pilot_max_in_flight" not in settings
    assert settings["auto_pilot_enabled"] == "true"
