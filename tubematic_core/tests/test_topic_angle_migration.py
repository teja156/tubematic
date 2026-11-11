"""The 0026 migration (TMDEV-214): videos.angle, angle_kind and angle_score.

No backfill, on purpose: '' means "no angle", which is true of every topic
filed before the upgrade, and such a topic stays usable (the agent adds an
angle when it picks the video up). The test that matters is that existing
videos keep everything they had.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402

NEW = ("angle", "angle_kind", "angle_score")
KEPT = ("status", "topic", "title", "producibility_score", "script", "formula_id")


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_before_0026(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_before_0026"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version < 26:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    rows = [
        ("proposed", "TOPIC_PROPOSED", "How a thing works", 7, ""),
        ("approved", "TOPIC_APPROVED", "Another thing", 6, ""),
        ("scripted", "SCRIPT_READY", "A third thing", 8, "One. Two."),
        ("manual", "TOPIC_PROPOSED", "A person's own topic", 0, ""),
    ]
    for vid, status, topic, score, script in rows:
        con.execute(
            "INSERT INTO videos (id, topic, title, status, producibility_score, script, "
            "created_at, updated_at) VALUES (?, ?, 'A title', ?, ?, ?, "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (vid, topic, status, score, script))
    con.commit()
    con.close()
    return db


def _rows(db, cols) -> dict:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out = {r["id"]: tuple(r[c] for c in cols)
           for r in con.execute(f"SELECT id, {', '.join(cols)} FROM videos")}
    con.close()
    return out


def test_existing_videos_have_no_angle_and_keep_everything_else(tmp_path):
    db = _db_before_0026(tmp_path)
    before = _rows(db, KEPT)
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    assert _rows(db, KEPT) == before
    assert set(_rows(db, NEW).values()) == {("", "", 0)}


def test_a_new_video_starts_with_no_angle(tmp_path):
    db = _db_before_0026(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) VALUES "
                "('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    assert _rows(db, NEW)["new"] == ("", "", 0)
