"""Tests for vqa/make_seed_db.py — the VQA image's build-time seed database."""
import json
import shutil
import sqlite3
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT / "vqa"))
sys.path.insert(0, str(REPO_ROOT / "renderer" / "api"))

from make_seed_db import VQA_PROJECT_ID, make_seed_db  # noqa: E402
from pipeline import _read_all_settings  # noqa: E402


@pytest.fixture()
def seed_db_path(tmp_path):
    path = tmp_path / "tubematic.db"
    make_seed_db(path)
    return path


def _columns(con, table):
    return {row[1] for row in con.execute(f"PRAGMA table_info({table})").fetchall()}


def test_schema_carries_current_migration_columns(seed_db_path):
    """Guards against silently reverting to a hand-written / stale schema copy
    (onboard/actions.py::_SCHEMA is already missing these columns)."""
    con = sqlite3.connect(str(seed_db_path))
    videos_cols = _columns(con, "videos")
    con.close()
    for col in ("voice_id", "ai_review_count", "render_fail_count", "script_segments",
                "producibility_score"):
        assert col in videos_cols, f"videos.{col} missing — seed DB schema is stale"
    assert "animatability_score" not in videos_cols


def test_gemini_review_disabled(seed_db_path):
    con = sqlite3.connect(str(seed_db_path))
    settings = _read_all_settings(con)
    con.close()
    assert settings["gemini_review_enabled"] is False


def test_default_voice_is_a_roster_member(seed_db_path):
    """The invariant _read_all_settings enforces on read: elevenlabs_voice_id
    must be "" or present in elevenlabs_voices. If seeding ever breaks this,
    _read_all_settings would silently blank the default rather than error —
    assert the roster membership directly so seeding bugs surface as a test
    failure, not as a silently-blanked default."""
    con = sqlite3.connect(str(seed_db_path))
    settings = _read_all_settings(con)
    con.close()
    assert settings["elevenlabs_voices"], "roster must be non-empty"
    roster_ids = {v["voice_id"] for v in settings["elevenlabs_voices"]}
    assert settings["elevenlabs_voice_id"] in roster_ids
    assert settings["elevenlabs_voice_id"] != "", "generate_voice hard-errors on a blank default"


def test_the_seeded_voice_carries_its_own_model(seed_db_path):
    """The seed is written after migrating, so migration 0006 never stamps it
    — it must already be in the per-voice shape, or every reader sees an
    empty roster and generate_voice refuses."""
    con = sqlite3.connect(str(seed_db_path))
    settings = _read_all_settings(con)
    rows = dict(con.execute("SELECT key, value FROM settings"))
    con.close()
    assert all(v["model_id"] == "eleven_multilingual_v2" for v in settings["elevenlabs_voices"])
    assert "elevenlabs_model_id" not in rows


def test_the_seeded_image_model_is_in_the_catalog(seed_db_path):
    from pipeline import OPENAI_IMAGE_MODELS
    con = sqlite3.connect(str(seed_db_path))
    settings = _read_all_settings(con)
    rows = dict(con.execute("SELECT key, value FROM settings").fetchall())
    con.close()
    assert settings["image_model"] in OPENAI_IMAGE_MODELS
    assert "image_provider" not in rows


def test_vqa_project_exists_and_active(seed_db_path):
    con = sqlite3.connect(str(seed_db_path))
    row = con.execute(
        "SELECT name, status, is_curriculum_seed FROM projects WHERE id = ?", (VQA_PROJECT_ID,)
    ).fetchone()
    con.close()
    assert row is not None
    name, status, is_curriculum_seed = row
    assert status == "active"
    assert is_curriculum_seed == 0


def test_generator_is_idempotent(tmp_path):
    path = tmp_path / "tubematic.db"
    make_seed_db(path)
    con = sqlite3.connect(str(path))
    project_count_1 = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    con.close()

    make_seed_db(path)  # re-run against the same path
    con = sqlite3.connect(str(path))
    project_count_2 = con.execute("SELECT COUNT(*) FROM projects").fetchone()[0]
    settings = _read_all_settings(con)
    con.close()

    assert project_count_1 == project_count_2 == 1
    assert settings["gemini_review_enabled"] is False


def test_survives_copy_of_db_file_alone(seed_db_path, tmp_path):
    """Regression test for the WAL-checkpoint requirement: kasm_post_run_user.sh copies
    only the .db file (never a -wal/-shm sidecar) into a fresh session's
    mounted/data/. If make_seed_db.py ever stopped checkpointing before
    close(), recent commits could sit in an uncommitted -wal file — invisible
    to a test that reopens the DB in place (the sidecar sits right next to it
    and is read transparently), but silently dropped by a copy-only-the-.db
    operation. Copying just the .db file into an isolated directory is the
    only way this bug would actually be caught."""
    sidecar_wal = seed_db_path.with_name(seed_db_path.name + "-wal")
    sidecar_shm = seed_db_path.with_name(seed_db_path.name + "-shm")
    assert not sidecar_wal.exists(), "seed DB must not leave a -wal sidecar behind"
    assert not sidecar_shm.exists(), "seed DB must not leave a -shm sidecar behind"

    isolated_dir = tmp_path / "copy_only"
    isolated_dir.mkdir()
    isolated_copy = isolated_dir / "tubematic.db"
    shutil.copy2(seed_db_path, isolated_copy)  # .db only, no sidecars to copy even if present

    con = sqlite3.connect(str(isolated_copy))
    settings = _read_all_settings(con)
    project = con.execute(
        "SELECT status FROM projects WHERE id = ?", (VQA_PROJECT_ID,)
    ).fetchone()
    con.close()

    assert settings["gemini_review_enabled"] is False
    assert settings["elevenlabs_voice_id"] != ""
    assert project == ("active",)
