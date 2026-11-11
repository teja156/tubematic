"""The 0022 migration (TMDEV-207): projects.default_agent_id,
default_agent_model and default_agent_effort, the agent a domain's new videos
start on.

No backfill, on purpose: '' means Automatic (the weighted deal), which is how
every domain worked before the upgrade. The test that matters is that an
existing domain comes through with all three blank and nothing else changed.
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


def _db_before_0022(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_before_0022"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version < 22:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute(
        "INSERT INTO projects (id, name, description, is_curriculum_seed, status, "
        "default_voice_id, topic_cap, created_at) "
        "VALUES ('seed', 'Seed', 'scope', 1, 'paused', 'v1', 250, '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    return db


def _project(db) -> dict:
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    row = dict(con.execute("SELECT * FROM projects WHERE id = 'seed'").fetchone())
    con.close()
    return row


def test_an_existing_domain_comes_through_on_automatic(tmp_path):
    db = _db_before_0022(tmp_path)
    assert "default_agent_id" not in _project(db)

    result = tdb.migrate(db)

    assert 22 in result.applied
    row = _project(db)
    assert (row["default_agent_id"], row["default_agent_model"],
            row["default_agent_effort"]) == ("", "", "")


def test_the_rest_of_the_domain_is_untouched(tmp_path):
    db = _db_before_0022(tmp_path)
    before = _project(db)

    tdb.migrate(db)

    after = _project(db)
    assert {k: after[k] for k in before} == before
