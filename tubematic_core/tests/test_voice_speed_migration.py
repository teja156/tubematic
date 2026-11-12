"""The 0030 migration (TMDEV-227): videos.voice_speed, a video's own speed.

No backfill: NULL means each voice speaks at its roster speed, which is how
every video voiced before the upgrade was made. What matters is that existing
and in-flight videos keep exactly what they had, and that a re-run is a no-op.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402

KEPT = ("status", "script", "voice_id", "voice_file_path", "timeline_path")


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_before_0030(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_before_0030"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version < 30:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, script, voice_id, voice_file_path, timeline_path, "
                "created_at, updated_at) VALUES ('voiced', 't', 'VOICE_READY', 'One. Two.', 'teja', "
                "'/jobs/voiced/audio.mp3', '/jobs/voiced/timeline.json', '2026-01-01T00:00:00Z', "
                "'2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    return db


def _rows(db, cols) -> dict:
    con = sqlite3.connect(db)
    out = {r[0]: tuple(r[1:]) for r in con.execute(f"SELECT id, {', '.join(cols)} FROM videos")}
    con.close()
    return out


def test_an_existing_video_keeps_its_voicing_and_has_no_speed_of_its_own(tmp_path):
    db = _db_before_0030(tmp_path)
    before = _rows(db, KEPT)
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    assert _rows(db, KEPT) == before
    assert _rows(db, ("voice_speed", "voiced_speed")) == {"voiced": (None, None)}


def test_a_new_video_starts_with_no_speed_of_its_own(tmp_path):
    db = _db_before_0030(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) VALUES "
                "('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    assert _rows(db, ("voice_speed",))["new"] == (None,)
