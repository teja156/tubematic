"""The 0015 image-model migration (TMDEV-166).

gemini-3-pro-image-preview was shut down and left the catalog. A stored value
would be coerced to the Gemini default on read, silently swapping a pro-tier
choice for flash, so the migration rewrites exactly that value to its GA
replacement and nothing else.
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


def _migrations_to(tmp_path, last: int) -> pathlib.Path:
    older = tmp_path / f"migrations_to_{last:04d}"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= last:
            shutil.copy(mig.path, older / mig.path.name)
    return older


def _migrate_through_0015(db, tmp_path):
    """Stop at 0015: 0016 (TMDEV-165) later moves every non-OpenAI image_model
    to an OpenAI one, which would mask what 0015 itself does."""
    older = tmp_path / "migrations_to_0015"
    if not older.exists():
        _migrations_to(tmp_path, 15)
    tdb.migrate(db, migrations_dir=older)


def _db_at_0014_with(tmp_path, settings: dict) -> pathlib.Path:
    older = _migrations_to(tmp_path, 14)
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


def test_a_stored_preview_moves_to_the_ga_model(tmp_path):
    db = _db_at_0014_with(tmp_path, {"image_provider": "gemini",
                                     "image_model": "gemini-3-pro-image-preview"})
    _migrate_through_0015(db, tmp_path)
    _migrate_through_0015(db, tmp_path)  # every process migrates on start; a second run is a no-op
    assert _settings(db)["image_model"] == "gemini-3-pro-image"
    assert _settings(db)["image_provider"] == "gemini"


@pytest.mark.parametrize("model", ["gemini-3.1-flash-image", "gpt-image-2.5-sunburst"])
def test_any_other_model_is_left_alone(tmp_path, model):
    db = _db_at_0014_with(tmp_path, {"image_model": model})
    _migrate_through_0015(db, tmp_path)
    assert _settings(db)["image_model"] == model


def test_only_the_image_model_key_is_rewritten(tmp_path):
    # A free-text setting that happens to hold the string must not be touched.
    db = _db_at_0014_with(tmp_path, {"user_preferences": "gemini-3-pro-image-preview"})
    _migrate_through_0015(db, tmp_path)
    assert _settings(db)["user_preferences"] == "gemini-3-pro-image-preview"
