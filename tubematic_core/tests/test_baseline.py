"""The 0001 baseline migration (TMDEV-91).

0001 is Python, not SQL, because it must converge a database at ANY historical
state — SQLite has no ADD COLUMN IF NOT EXISTS, so the guarded ALTERs cannot be
expressed in a .sql file. It is today's already-idempotent _init_db, frozen.
"""
import pathlib
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures" / "db"

EXPECTED_TABLES = {
    "projects", "videos", "agents", "agent_deck", "comments", "settings",
    "script_profiles", "script_profile_transcripts",
    "video_publications", "video_metrics", "schema_migrations",
}

EXPECTED_VIDEO_COLUMNS = {
    "id", "project_id", "topic", "strategy", "producibility_score", "status",
    "title", "script", "voice_file_path", "timeline_path", "scene_config_path",
    "video_path", "video_version", "gemini_feedback", "youtube_url", "voice_id",
    "notified_status", "tts_text", "agent_model", "agent_id",
    "cost_cents_elevenlabs", "cost_cents_gemini", "cost_cents_claude",
    "created_at", "updated_at", "ai_review_count", "render_fail_count",
    "script_segments", "script_profile_id", "publish_title",
    "publish_description", "archived_at", "visual_style", "resolved_visual_style",
    "agent_effort", "agent_no_progress_count", "agent_stuck_at", "agent_last_outcome_key",
}

EXPECTED_PROJECT_COLUMNS = {
    "id", "name", "description", "is_curriculum_seed", "status", "created_at",
    "default_visual_style",
}


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _tables(db):
    con = sqlite3.connect(db)
    out = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    con.close()
    return out


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


# ── fresh database ───────────────────────────────────────────────────────────

def test_a_fresh_database_gets_every_table(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    assert EXPECTED_TABLES <= _tables(db)


def test_a_fresh_database_gets_every_videos_column(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    assert EXPECTED_VIDEO_COLUMNS <= _columns(db, "videos")


def test_a_fresh_database_is_stamped_at_one(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    assert tdb.current_schema_version(db) >= 1


# ── old databases ────────────────────────────────────────────────────────────

def test_pre_agents_database_converges(tmp_path):
    db = _from_fixture(tmp_path, "pre_agents.sql")
    tdb.migrate(db)
    assert EXPECTED_TABLES <= _tables(db)
    assert EXPECTED_VIDEO_COLUMNS <= _columns(db, "videos")


def test_pre_agents_database_keeps_its_rows(tmp_path):
    db = _from_fixture(tmp_path, "pre_agents.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT COUNT(*) FROM videos").fetchone()[0] == 3
    assert con.execute("SELECT COUNT(*) FROM projects").fetchone()[0] == 1
    assert con.execute("SELECT topic FROM videos WHERE id='vid_a'").fetchone()[0] == "Alpha"
    con.close()


def test_pre_publishing_database_converges(tmp_path):
    db = _from_fixture(tmp_path, "pre_publishing.sql")
    tdb.migrate(db)
    assert EXPECTED_TABLES <= _tables(db)
    assert EXPECTED_VIDEO_COLUMNS <= _columns(db, "videos")


def test_the_animatability_rename_carries_its_values(tmp_path):
    """A rename, not a drop-and-add: the scores must survive."""
    db = _from_fixture(tmp_path, "pre_publishing.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert "animatability_score" not in _columns(db, "videos")
    assert con.execute(
        "SELECT producibility_score FROM videos WHERE id='vid_old'").fetchone()[0] == 7
    con.close()


def test_a_user_set_setting_is_not_overwritten(tmp_path):
    """Migrations preserve user data. A default must never clobber a set value."""
    db = _from_fixture(tmp_path, "pre_agents.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT value FROM settings WHERE key='elevenlabs_voice_id'").fetchone()[0] == "my-voice"
    con.close()


def test_the_render_retry_key_is_renamed_not_duplicated(tmp_path):
    db = _from_fixture(tmp_path, "pre_agents.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT value FROM settings WHERE key='max_render_retries'").fetchone()[0] == "3"
    assert not con.execute(
        "SELECT 1 FROM settings WHERE key='max_feedback_loops'").fetchone()
    con.close()


def test_stranded_scripting_rows_are_recovered(tmp_path):
    """This statement exists only in mcp/server.py's copy today. Losing it in the
    merge would strand any row still sitting at the removed SCRIPTING status."""
    db = _from_fixture(tmp_path, "pre_agents.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute(
        "SELECT status FROM videos WHERE id='vid_stranded'").fetchone()[0] == "TOPIC_APPROVED"
    con.close()


def test_the_retired_agent_model_setting_is_deleted(tmp_path):
    """This statement exists only in pipeline.py's copy today. It must survive the
    merge, or the settings API 400s on an unknown key."""
    db = _from_fixture(tmp_path, "pre_agents.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert not con.execute("SELECT 1 FROM settings WHERE key='agent_model'").fetchone()
    con.close()


def test_notified_status_is_backfilled_not_left_blank(tmp_path):
    """Without the backfill the first notification sweep after an upgrade
    announces every parked video at once. The composed form is load-bearing."""
    db = _from_fixture(tmp_path, "pre_publishing.sql")
    tdb.migrate(db)
    con = sqlite3.connect(db)
    marker, status, updated = con.execute(
        "SELECT notified_status, status, updated_at FROM videos WHERE id='vid_old'"
    ).fetchone()
    con.close()
    assert marker == f"{status}@{updated}"


def test_migrating_twice_changes_nothing(tmp_path):
    db = _from_fixture(tmp_path, "pre_agents.sql")
    tdb.migrate(db)
    first = _columns(db, "videos")
    assert tdb.migrate(db).applied == []
    assert _columns(db, "videos") == first
