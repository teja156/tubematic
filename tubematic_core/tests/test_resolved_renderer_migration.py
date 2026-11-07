"""The 0017 migration (TMDEV-179): videos.resolved_renderer, which renderer
`auto` settled on, with its load-bearing backfill.

ADD COLUMN applies its DEFAULT ('') to every existing row, and '' means
"auto has not settled yet". Left there, every in-flight video would read as
unresolved and a revision round could decide a half-authored DOM video is now
Cartoon 3D and throw its scenes away. Every video that exists before the
migration predates the style, so the migration marks them all 'dom'.
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


def _db_at_0016_with_videos(tmp_path, ids) -> pathlib.Path:
    older = tmp_path / "migrations_to_0016"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 16:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    for vid in ids:
        con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                    "VALUES (?, 't', 'VOICE_READY', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')", (vid,))
    con.commit()
    con.close()
    return db


def _renderers(db) -> dict:
    con = sqlite3.connect(db)
    rows = dict(con.execute("SELECT id, resolved_renderer FROM videos").fetchall())
    con.close()
    return rows


def test_every_existing_video_is_backfilled_to_dom(tmp_path):
    db = _db_at_0016_with_videos(tmp_path, ["v1", "v2"])
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    assert _renderers(db) == {"v1": "dom", "v2": "dom"}


def test_a_video_created_after_the_migration_starts_unresolved(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    assert _renderers(db) == {"new": ""}
