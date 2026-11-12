"""The 0020 migration (TMDEV-203): videos.style_pick, style_runner_up and
style_reason, what Auto picked for a video's style before its script.

No backfill, on purpose: '' means "Auto has not decided", which is true of
every video filed before the upgrade. One already scripted finishes the way
Auto worked then; one not yet scripted is routed when the agent picks it up.
The test that matters is that no in-flight row changes, above all its
visual_style and its recorded renderer and canvas.
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


def _db_at_0019(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_to_0019"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 19:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    rows = [
        ("topic", "TOPIC_APPROVED", "auto", "", ""),
        ("scripted", "SCRIPT_READY", "auto", "", ""),
        ("mid_scenes", "REVISION_REQUESTED", "auto", "dark", "dom"),
        ("world", "VIDEO_READY", "auto", "", "cartoon_3d"),
        ("forced", "VOICE_READY", "system_flow", "", ""),
    ]
    for vid, status, style, canvas, renderer in rows:
        con.execute(
            "INSERT INTO videos (id, topic, status, visual_style, resolved_visual_style, "
            "resolved_renderer, created_at, updated_at) VALUES (?, 't', ?, ?, ?, ?, "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (vid, status, style, canvas, renderer))
    con.commit()
    con.close()
    return db


def _rows(db) -> dict:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out = {r["id"]: dict(r) for r in con.execute(
        "SELECT id, status, visual_style, resolved_visual_style, resolved_renderer, "
        "style_pick, style_runner_up, style_reason FROM videos")}
    con.close()
    return out


def test_existing_videos_read_as_not_decided_and_keep_everything_else(tmp_path):
    db = _db_at_0019(tmp_path)
    con = sqlite3.connect(db)
    before = {r[0]: r[1:] for r in con.execute(
        "SELECT id, status, visual_style, resolved_visual_style, resolved_renderer FROM videos")}
    con.close()
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    rows = _rows(db)
    for vid, (status, style, canvas, renderer) in before.items():
        row = rows[vid]
        assert (row["status"], row["visual_style"], row["resolved_visual_style"],
                row["resolved_renderer"]) == (status, style, canvas, renderer)
        assert (row["style_pick"], row["style_runner_up"], row["style_reason"]) == ("", "", "")


def test_a_new_video_starts_not_decided(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    assert _rows(db)["new"]["style_pick"] == ""
