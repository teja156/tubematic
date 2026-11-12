"""The 0024 migration (TMDEV-212): videos.duration_secs, the published
video's length in seconds.

No backfill: a migration sees the database and not the jobs folder, so every
existing row reads NULL (not known) and the worker fills what it still can.
NULL and not 0 is the point: a 0 would be a length, and Analytics would divide
by it or show a share for a video it knows nothing about.
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


def _db_before_0024(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_before_0024"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version < 24:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    for vid, status in [("published", "PUBLISHED"), ("topic", "TOPIC_PROPOSED")]:
        con.execute(
            "INSERT INTO videos (id, topic, status, script, created_at, updated_at) "
            "VALUES (?, 't', ?, 'a script', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (vid, status))
    con.commit()
    con.close()
    return db


def test_existing_videos_have_an_unknown_length_and_keep_everything_else(tmp_path):
    db = _db_before_0024(tmp_path)
    con = sqlite3.connect(db)
    before = {r[0]: r[1:] for r in con.execute("SELECT id, status, script, updated_at FROM videos")}
    con.close()
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    con = sqlite3.connect(db)
    after = {r[0]: r[1:] for r in con.execute("SELECT id, status, script, updated_at FROM videos")}
    lengths = [r[0] for r in con.execute("SELECT duration_secs FROM videos")]
    con.close()
    assert after == before
    assert lengths == [None, None]


def test_a_new_video_starts_with_an_unknown_length(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    row = con.execute("SELECT duration_secs FROM videos WHERE id = 'new'").fetchone()
    con.close()
    assert row == (None,)
