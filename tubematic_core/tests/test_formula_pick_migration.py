"""The 0025 migration (TMDEV-213): the formula decision made before the
script (videos.formula_choice, formula_pick, formula_runner_up,
formula_reason) and a domain's default formula (projects.default_formula_id).

No backfill, on purpose: '' means "Auto" for a choice and "not decided" for a
pick, which is true of every video and domain that existed before the upgrade.
The test that matters is that a video already scripted keeps its script and
the formula recorded with it, since nothing may send it back to be picked for.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402

NEW = ("formula_choice", "formula_pick", "formula_runner_up", "formula_reason")
KEPT = ("status", "script", "formula_id", "hook_type", "visual_style", "style_pick")


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_before_0025(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_before_0025"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version < 25:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO projects (id, name, created_at) VALUES "
                "('dom', 'A domain', '2026-01-01T00:00:00Z')")
    rows = [
        ("proposed", "TOPIC_PROPOSED", "", "", ""),
        ("approved", "TOPIC_APPROVED", "", "", "system_flow"),
        ("scripted", "SCRIPT_READY", "One. Two.", "scene-story", ""),
        ("published", "PUBLISHED", "Old words.", "", ""),
    ]
    for vid, status, script, formula, pick in rows:
        con.execute(
            "INSERT INTO videos (id, topic, status, script, formula_id, style_pick, project_id, "
            "created_at, updated_at) VALUES (?, 't', ?, ?, ?, ?, 'dom', "
            "'2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')",
            (vid, status, script, formula, pick))
    con.commit()
    con.close()
    return db


def _rows(db, cols, table="videos") -> dict:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    out = {r["id"]: tuple(r[c] for c in cols)
           for r in con.execute(f"SELECT id, {', '.join(cols)} FROM {table}")}
    con.close()
    return out


def test_existing_videos_have_no_pick_and_keep_their_script_and_record(tmp_path):
    db = _db_before_0025(tmp_path)
    before = _rows(db, KEPT)
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    assert _rows(db, KEPT) == before
    assert set(_rows(db, NEW).values()) == {("", "", "", "")}


def test_an_existing_domain_is_on_auto(tmp_path):
    db = _db_before_0025(tmp_path)
    tdb.migrate(db)
    assert _rows(db, ("default_formula_id",), "projects") == {"dom": ("",)}


def test_a_new_video_starts_with_no_choice_and_no_pick(tmp_path):
    db = _db_before_0025(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) VALUES "
                "('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    assert _rows(db, NEW)["new"] == ("", "", "", "")
