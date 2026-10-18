"""The 0008 scheduled-publishing migration (TMDEV-133).

Every existing video must come out "not scheduled" (''), because the worker's
due-time pass selects on scheduled_at — a NULL or a stray value there would be
read as a schedule.
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


def test_existing_videos_are_not_scheduled(tmp_path):
    older = tmp_path / "migrations_to_0007"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 7:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, strategy, producibility_score, status, "
                "created_at, updated_at) VALUES ('v1', 't', 'manual', 5, 'VIDEO_APPROVED', "
                "'2026-01-01', '2026-01-01')")
    con.commit()
    con.close()

    tdb.migrate(db)

    con = sqlite3.connect(db)
    row = con.execute("SELECT scheduled_at, scheduled_timezone FROM videos "
                      "WHERE id = 'v1'").fetchone()
    con.close()
    assert row == ("", "")
