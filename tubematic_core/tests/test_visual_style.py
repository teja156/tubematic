"""The 0002 visual-style migration (TMDEV-101).

The backfill is the whole point of these tests. `ALTER TABLE ... ADD COLUMN
... DEFAULT 'auto'` applies its default to every EXISTING row, so without the
trailing UPDATE every video already in flight would quietly become 'auto' and
be re-styled by the next agent run that touched it. Dropping that one line
leaves a migration that still adds the right columns and still passes any test
that only checks the schema.
"""
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "db"


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _columns(db, table):
    con = sqlite3.connect(db)
    out = {r[1] for r in con.execute(f"PRAGMA table_info({table})")}
    con.close()
    return out


def _from_fixture(tmp_path, name):
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript((FIXTURES / name).read_text())
    con.commit()
    con.close()
    return db


def test_a_fresh_database_gets_all_three_columns(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    assert {"visual_style", "resolved_visual_style"} <= _columns(db, "videos")
    assert "default_visual_style" in _columns(db, "projects")


def test_the_migration_is_recorded(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    assert tdb.current_schema_version(db) >= 2


def test_running_it_twice_changes_nothing(tmp_path):
    """Every process calls migrate() on start; a second run must be a no-op."""
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO projects (id, name, created_at) VALUES ('p1', 'P', '2026-01-01T00:00:00Z')")
    con.execute(
        "INSERT INTO videos (id, topic, status, visual_style, created_at, updated_at) "
        "VALUES ('v1', 'T', 'TOPIC_PROPOSED', 'stick', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z')")
    con.commit()
    con.close()

    tdb.migrate(db)

    con = sqlite3.connect(db)
    assert con.execute("SELECT visual_style FROM videos WHERE id='v1'").fetchone()[0] == "stick"
    con.close()


def test_existing_videos_are_backfilled_to_motion_graphics(tmp_path):
    """The regression this migration is most likely to grow.

    An existing video was authored, and possibly already rendered, under the
    only register that existed. Leaving it at the column default ('auto') hands
    the agent permission to pick a different one on the next revision round.
    """
    db = _from_fixture(tmp_path, "pre_publishing.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    styles = {r[0] for r in con.execute("SELECT visual_style FROM videos")}
    count = con.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    con.close()
    assert count > 0, "fixture must actually contain videos or this proves nothing"
    assert styles == {"motion_graphics"}


def test_existing_videos_keep_their_other_columns(tmp_path):
    db = _from_fixture(tmp_path, "pre_publishing.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT topic FROM videos WHERE id='vid_old'").fetchone()[0] is not None
    con.close()


def test_a_video_created_after_the_migration_defaults_to_auto(tmp_path):
    """The backfill must not become the column default for new rows."""
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO videos (id, topic, status, created_at, updated_at) "
        "VALUES ('v2', 'T', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    row = con.execute(
        "SELECT visual_style, resolved_visual_style FROM videos WHERE id='v2'").fetchone()
    con.close()
    assert row == ("auto", "")


def test_a_project_defaults_to_no_style(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO projects (id, name, created_at) VALUES ('p2', 'P', '2026-01-01T00:00:00Z')")
    con.commit()
    value = con.execute(
        "SELECT default_visual_style FROM projects WHERE id='p2'").fetchone()[0]
    con.close()
    assert value == ""
