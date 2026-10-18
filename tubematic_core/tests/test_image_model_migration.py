"""The 0011 image-model migration (TMDEV-148).

gpt-image-2 left the catalog. A stored `image_model = 'gpt-image-2'` that
survived the upgrade would make every later settings save 400 on the
provider/model cross-check, so the migration rewrites exactly that value and
nothing else.
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


def _migrate_through_0011(db, tmp_path):
    """Stop at 0011: 0016 later rewrites every non-OpenAI image_model, which
    would mask what 0011 itself does."""
    tdb.migrate(db, migrations_dir=_migrations_to(tmp_path, 11))


def _db_at_0010_with(tmp_path, settings: dict) -> pathlib.Path:
    older = _migrations_to(tmp_path, 10)
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


def test_a_stored_gpt_image_2_moves_to_flare(tmp_path):
    db = _db_at_0010_with(tmp_path, {"image_provider": "openai", "image_model": "gpt-image-2"})
    _migrate_through_0011(db, tmp_path)
    tdb.migrate(db, migrations_dir=tmp_path / "migrations_to_0011")  # a second run is a no-op
    assert _settings(db)["image_model"] == "gpt-image-2.5-flare"
    assert _settings(db)["image_provider"] == "openai"


@pytest.mark.parametrize("model", ["gemini-3.1-flash-image", "gpt-image-2.5-sunburst"])
def test_any_other_model_is_left_alone(tmp_path, model):
    db = _db_at_0010_with(tmp_path, {"image_model": model})
    _migrate_through_0011(db, tmp_path)
    assert _settings(db)["image_model"] == model


def test_only_the_image_model_key_is_rewritten(tmp_path):
    # A free-text setting that happens to hold the string must not be touched.
    db = _db_at_0010_with(tmp_path, {"user_preferences": "gpt-image-2"})
    _migrate_through_0011(db, tmp_path)
    assert _settings(db)["user_preferences"] == "gpt-image-2"
