"""The 0007 agent-progress migration (TMDEV-129).

Two things: the videos table gains the poller's no-progress count and stuck
flag, with a clean record for every existing video; and every agent session
recorded under the VOICING stage before the upgrade is relabelled, because the
old poller carried a voicing session on into scene writing, and the dashboard
would otherwise present that spend as voicing alone.
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


def _db_at_0006(tmp_path):
    older = tmp_path / "migrations_to_0006"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 6:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, strategy, producibility_score, status, "
                "created_at, updated_at) VALUES ('v1', 't', 'manual', 5, 'VOICE_READY', "
                "'2026-01-01', '2026-01-01')")
    for i, (stage, video) in enumerate([("VOICING", "v1"), ("TOPIC_APPROVED", "v1"),
                                        ("VOICING", "v2"), (None, "v1")], start=1):
        con.execute("INSERT INTO usage_events (id, created_at, service, operation, "
                    "cost_basis) VALUES (?, '2026-01-01', 'anthropic', 'agent_pipeline', "
                    "'list')", (i,))
        con.execute("INSERT INTO usage_event_videos (event_id, video_id, stage) "
                    "VALUES (?, ?, ?)", (i, video, stage))
    con.commit()
    con.close()
    return db


def _stages(db):
    con = sqlite3.connect(db)
    rows = con.execute("SELECT event_id, stage FROM usage_event_videos ORDER BY event_id")
    out = rows.fetchall()
    con.close()
    return out


def test_existing_videos_start_with_a_clean_record(tmp_path):
    db = _db_at_0006(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    row = con.execute("SELECT agent_no_progress_count, agent_stuck_at FROM videos").fetchone()
    con.close()
    assert row == (0, None)


def test_only_voicing_sessions_are_relabelled_as_voicing_with_scenes(tmp_path):
    db = _db_at_0006(tmp_path)
    tdb.migrate(db)
    assert _stages(db) == [(1, "VOICING_WITH_SCENES"), (2, "TOPIC_APPROVED"),
                           (3, "VOICING_WITH_SCENES"), (4, None)]


def test_a_voicing_session_recorded_after_the_upgrade_keeps_its_stage(tmp_path):
    """The relabel runs once: a row the new, one-stage poller writes is voicing only."""
    db = _db_at_0006(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO usage_events (id, created_at, service, operation, cost_basis) "
                "VALUES (9, '2026-10-01', 'anthropic', 'agent_pipeline', 'list')")
    con.execute("INSERT INTO usage_event_videos (event_id, video_id, stage) "
                "VALUES (9, 'v1', 'VOICING')")
    con.commit()
    con.close()
    tdb.migrate(db)
    assert (9, "VOICING") in _stages(db)
