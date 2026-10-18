"""The 0003 agent-effort migration (TMDEV-106).

Unlike 0002, this migration deliberately has no backfill, and the tests here
exist mostly to keep it that way in both directions: an existing video must end
up at '' (follow your agent), an existing agent at 'high', and neither may be
"corrected" by a later UPDATE that someone adds by analogy with 0002.
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


def test_a_fresh_database_gets_both_columns(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    assert "agent_effort" in _columns(db, "videos")
    assert "effort" in _columns(db, "agents")


def test_the_migration_is_recorded(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    assert tdb.current_schema_version(db) >= 3


def test_a_new_video_follows_its_agent(tmp_path):
    """'' is not "unset" — it is the value that means "use the agent's"."""
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO videos (id, topic, status, created_at, updated_at) "
        "VALUES ('v1', 'T', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    value = con.execute("SELECT agent_effort FROM videos WHERE id='v1'").fetchone()[0]
    con.close()
    assert value == ""


def test_a_new_agent_defaults_to_high(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO agents (id, name, binary, run_path, created_at, updated_at) "
        "VALUES ('claude', 'Claude Code', 'claude', '/tmp/a', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z')")
    con.commit()
    value = con.execute("SELECT effort FROM agents WHERE id='claude'").fetchone()[0]
    con.close()
    assert value == "high"


def test_existing_videos_are_not_backfilled(tmp_path):
    """The mirror image of 0002's backfill test.

    A pre-0003 video has no per-video pick to preserve, so writing anything but
    '' would pin it to a level nobody chose and freeze it there at its next
    status change. An UPDATE added here "for symmetry with 0002" is the bug
    this catches.
    """
    db = _from_fixture(tmp_path, "pre_publishing.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    efforts = {r[0] for r in con.execute("SELECT agent_effort FROM videos")}
    count = con.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
    con.close()
    assert count > 0, "fixture must actually contain videos or this proves nothing"
    assert efforts == {""}


def test_an_existing_install_runs_at_high(tmp_path):
    """Rule 1 from the ticket, on the upgrade path rather than a fresh install.

    `ADD COLUMN ... DEFAULT 'high'` applies to existing rows, which is what
    makes "an install that never touches the setting runs at high" true for an
    agent installed before this migration existed.
    """
    db = _from_fixture(tmp_path, "pre_publishing.sql")
    con = sqlite3.connect(db)
    con.execute(
        "CREATE TABLE IF NOT EXISTS agents (id TEXT PRIMARY KEY, name TEXT NOT NULL, "
        "binary TEXT NOT NULL, run_path TEXT NOT NULL, created_at TEXT NOT NULL, "
        "updated_at TEXT NOT NULL)")
    con.execute(
        "INSERT INTO agents (id, name, binary, run_path, created_at, updated_at) "
        "VALUES ('claude', 'Claude Code', 'claude', '/tmp/a', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z')")
    con.commit()
    con.close()

    tdb.migrate(db)

    con = sqlite3.connect(db)
    value = con.execute("SELECT effort FROM agents WHERE id='claude'").fetchone()[0]
    con.close()
    assert value == "high"


def test_running_it_twice_changes_nothing(tmp_path):
    """Every process calls migrate() on start; a second run must be a no-op."""
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO videos (id, topic, status, agent_effort, created_at, updated_at) "
        "VALUES ('v1', 'T', 'TOPIC_PROPOSED', 'max', '2026-01-01T00:00:00Z', "
        "'2026-01-01T00:00:00Z')")
    con.commit()
    con.close()

    tdb.migrate(db)

    con = sqlite3.connect(db)
    assert con.execute("SELECT agent_effort FROM videos WHERE id='v1'").fetchone()[0] == "max"
    con.close()
