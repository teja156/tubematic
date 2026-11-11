"""The 0023 migration (TMDEV-211): videos.formula_id, hook_type,
hook_alternatives and script_warnings, what a script was built on.

No backfill, on purpose: '' means "no formula on record", which is true of
every script written before the upgrade. The test that matters is that a video
already scripted, voiced or published keeps its script and everything else.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402

NEW = ("formula_id", "hook_type", "hook_alternatives", "script_warnings")
KEPT = ("status", "script", "script_segments", "publish_title", "visual_style")


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_before_0023(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_before_0023"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version < 23:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    rows = [
        ("proposed", "TOPIC_PROPOSED", "", None, ""),
        ("scripted", "SCRIPT_READY", "One. Two.", '[{"id":"seg-1","voice":"One. Two.","visual":""}]', "A title"),
        ("flat", "VIDEO_READY", "A flat script.", None, ""),
        ("published", "PUBLISHED", "Old words. Follow for more.", None, "Posted"),
    ]
    for vid, status, script, segments, title in rows:
        con.execute(
            "INSERT INTO videos (id, topic, status, script, script_segments, publish_title, "
            "created_at, updated_at) VALUES (?, 't', ?, ?, ?, ?, "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (vid, status, script, segments, title))
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


def test_existing_videos_have_no_record_and_keep_their_script(tmp_path):
    db = _db_before_0023(tmp_path)
    before = _rows(db, KEPT)
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    assert _rows(db, KEPT) == before
    assert set(_rows(db, NEW).values()) == {("", "", "", "")}


def test_a_new_video_starts_with_no_record(tmp_path):
    db = _db_before_0023(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) VALUES "
                "('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    assert _rows(db, NEW)["new"] == ("", "", "", "")
