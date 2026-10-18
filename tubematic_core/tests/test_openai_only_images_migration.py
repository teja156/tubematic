"""The 0016 image migration (TMDEV-165).

OpenAI became the only image provider. The MCP server reads image_model raw,
so any stored value outside the OpenAI catalog would make every generate_image
refuse; the migration moves it to the default and deletes the retired
image_provider row.
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


def _db_at_0015_with(tmp_path, settings: dict) -> pathlib.Path:
    older = tmp_path / "migrations_to_0015"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 15:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.executemany("INSERT INTO settings (key, value) VALUES (?, ?)", settings.items())
    con.commit()
    con.close()
    return db


def _settings(db) -> dict:
    con = sqlite3.connect(db)
    rows = dict(con.execute("SELECT key, value FROM settings").fetchall())
    con.close()
    return rows


@pytest.mark.parametrize("stored", [
    "gemini-2.5-flash-image", "gemini-3.1-flash-image", "gemini-3-pro-image",
    # Not only the Gemini names: any off-catalog value would wedge generate_image.
    "something-hand-edited",
])
def test_a_non_openai_image_model_moves_to_flare(tmp_path, stored):
    db = _db_at_0015_with(tmp_path, {"image_provider": "gemini", "image_model": stored})
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    rows = _settings(db)
    assert rows["image_model"] == "gpt-image-2.5-flare"
    assert "image_provider" not in rows


@pytest.mark.parametrize("model", ["gpt-image-2.5-flare", "gpt-image-2.5-sunburst"])
def test_an_openai_model_is_kept(tmp_path, model):
    db = _db_at_0015_with(tmp_path, {"image_provider": "openai", "image_model": model})
    tdb.migrate(db)
    rows = _settings(db)
    assert rows["image_model"] == model
    assert "image_provider" not in rows


def test_an_install_that_never_stored_either_key_gets_nothing_written(tmp_path):
    """Absent rows resolve to the new spec default at read time."""
    db = _db_at_0015_with(tmp_path, {})
    tdb.migrate(db)
    rows = _settings(db)
    assert "image_model" not in rows and "image_provider" not in rows


def test_other_keys_holding_the_same_strings_are_untouched(tmp_path):
    db = _db_at_0015_with(tmp_path, {"user_preferences": "gemini-2.5-flash-image",
                                     "character_model": "gpt-image-2.5-sunburst",
                                     "ai_review_model": "gemini-2.5-flash"})
    tdb.migrate(db)
    rows = _settings(db)
    assert rows["user_preferences"] == "gemini-2.5-flash-image"
    assert rows["character_model"] == "gpt-image-2.5-sunburst"
    assert rows["ai_review_model"] == "gemini-2.5-flash"
