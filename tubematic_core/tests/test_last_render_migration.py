"""The 0021 migration (TMDEV-206): videos.last_render_renderer_id,
last_render_renderer_name, last_render_on_gpu and last_render_seconds, the
record of a video's last successful render.

No backfill: no earlier version kept which renderer made a video, so every
existing row reads as "no record" and the dashboard hides its rows. The test
that matters is that no existing row changes otherwise.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402

_RECORD = ("last_render_renderer_id", "last_render_renderer_name", "last_render_on_gpu", "last_render_seconds")


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_at_0020(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_to_0020"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 20:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    for vid, status, uploaded in [("ready", "VIDEO_READY", "2026-01-01T00:05:00Z"),
                                  ("rendering", "RENDERING", ""),
                                  ("topic", "TOPIC_PROPOSED", "")]:
        con.execute(
            "INSERT INTO videos (id, topic, status, render_started_at, render_uploaded_at, created_at, updated_at) "
            "VALUES (?, 't', ?, '2026-01-01T00:00:00Z', ?, '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (vid, status, uploaded))
    con.commit()
    con.close()
    return db


def test_existing_videos_have_no_record_and_keep_everything_else(tmp_path):
    db = _db_at_0020(tmp_path)
    con = sqlite3.connect(db)
    before = {r[0]: r[1:] for r in con.execute(
        "SELECT id, status, render_started_at, render_uploaded_at, updated_at FROM videos")}
    con.close()
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    con = sqlite3.connect(db)
    after = {r[0]: r[1:] for r in con.execute(
        "SELECT id, status, render_started_at, render_uploaded_at, updated_at FROM videos")}
    records = {r[0]: r[1:] for r in con.execute(f"SELECT id, {', '.join(_RECORD)} FROM videos")}
    con.close()
    assert after == before
    assert set(records.values()) == {("", "", 0, 0)}


def test_a_new_video_starts_with_no_record(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    row = con.execute(f"SELECT {', '.join(_RECORD)} FROM videos WHERE id = 'new'").fetchone()
    con.close()
    assert row == ("", "", 0, 0)
