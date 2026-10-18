"""The 0006 voice-models migration (TMDEV-121).

The install-wide elevenlabs_model_id row is replaced by a model on every roster
voice. The property that matters most is that an upgrade changes nothing a
user can hear: every voice must come out on the model the install was using.
The next is that it never destroys a roster — the readers treat a malformed
roster as empty, so a bad stamp would silently drop every voice.
"""
import json
import pathlib
import shutil
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_at_0005(tmp_path, settings: dict):
    older = tmp_path / "migrations_to_0005"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 5:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", settings.items())
    con.execute("INSERT INTO projects (id, name, created_at) VALUES ('p', 'P', '2026-01-01')")
    con.commit()
    con.close()
    return db


def _setting(db, key):
    con = sqlite3.connect(db)
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    con.close()
    return row[0] if row else None


ROSTER = [{"name": "Rachel", "voice_id": "r1"}, {"name": "Adam", "voice_id": "a1"}]


def test_every_voice_gets_the_install_model(tmp_path):
    db = _db_at_0005(tmp_path, {"elevenlabs_voices": json.dumps(ROSTER),
                                "elevenlabs_model_id": "eleven_v3"})
    tdb.migrate(db)
    roster = json.loads(_setting(db, "elevenlabs_voices"))
    assert [v["model_id"] for v in roster] == ["eleven_v3", "eleven_v3"]
    assert [(v["name"], v["voice_id"]) for v in roster] == [("Rachel", "r1"), ("Adam", "a1")]


def test_the_install_wide_model_row_is_deleted(tmp_path):
    db = _db_at_0005(tmp_path, {"elevenlabs_voices": json.dumps(ROSTER),
                                "elevenlabs_model_id": "eleven_v3"})
    tdb.migrate(db)
    assert _setting(db, "elevenlabs_model_id") is None


@pytest.mark.parametrize("stored", ["", "eleven_english_v1", None])
def test_a_blank_retired_or_missing_model_falls_back_to_multilingual_v2(tmp_path, stored):
    settings = {"elevenlabs_voices": json.dumps(ROSTER)}
    if stored is not None:
        settings["elevenlabs_model_id"] = stored
    db = _db_at_0005(tmp_path, settings)
    tdb.migrate(db)
    roster = json.loads(_setting(db, "elevenlabs_voices"))
    assert {v["model_id"] for v in roster} == {"eleven_multilingual_v2"}


def test_a_voice_that_already_has_a_valid_model_keeps_it(tmp_path):
    roster = [{"name": "Rachel", "voice_id": "r1", "model_id": "eleven_flash_v2"},
              {"name": "Adam", "voice_id": "a1"}]
    db = _db_at_0005(tmp_path, {"elevenlabs_voices": json.dumps(roster),
                                "elevenlabs_model_id": "eleven_v3"})
    tdb.migrate(db)
    out = json.loads(_setting(db, "elevenlabs_voices"))
    assert [v["model_id"] for v in out] == ["eleven_flash_v2", "eleven_v3"]


def test_a_corrupt_roster_is_left_untouched(tmp_path):
    db = _db_at_0005(tmp_path, {"elevenlabs_voices": "{not json",
                                "elevenlabs_model_id": "eleven_v3"})
    tdb.migrate(db)
    assert _setting(db, "elevenlabs_voices") == "{not json"


def test_a_fresh_database_without_settings_rows_migrates(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db)
    assert _setting(db, "elevenlabs_voices") is None
    assert tdb.current_schema_version(db) >= 6


def test_projects_gain_an_empty_default_voice(tmp_path):
    db = _db_at_0005(tmp_path, {})
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT default_voice_id FROM projects WHERE id = 'p'").fetchone() == ("",)
    con.close()
