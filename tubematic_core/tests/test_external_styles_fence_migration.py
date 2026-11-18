"""The 0031 migration (TMDEV-252): the rollback fence for external styles.

A video in an installed external style stores an `ext_...` id in
videos.visual_style, which 2.3.x does not know: it would render that video
blank. 0031 changes no data. It raises the schema version, so the upgrade takes
a backup, and 2.3.x's upgrade.py refuses the newer database until that backup is
restored (Rollback policy). What matters is that the fence stays above 2.3.x's
newest migration and that it leaves every row as it was.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402

FENCE = 31
NEWEST_IN_2_3 = 30  # 0030_voice_speed.sql, the last migration v2.3.0 and v2.3.1 ship


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_at_2_3(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_2_3"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= NEWEST_IN_2_3:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, visual_style, created_at, updated_at) VALUES "
                "('v1', 't', 'VOICE_READY', 'night_signal', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    return db


def _dump(db) -> list:
    con = sqlite3.connect(db)
    rows = list(con.iterdump())
    con.close()
    return [r for r in rows if "schema_migrations" not in r]


def test_the_fence_sits_above_the_newest_migration_2_3_ships():
    versions = [m.version for m in tdb.discover()]
    assert FENCE in versions
    assert FENCE > NEWEST_IN_2_3
    fence = next(m for m in tdb.discover() if m.version == FENCE)
    assert fence.path.name == "0031_external_styles_fence.py"


def test_an_upgrade_from_2_3_takes_a_backup_and_changes_no_data(tmp_path):
    db = _db_at_2_3(tmp_path)
    before = _dump(db)
    result = tdb.migrate(db)
    assert FENCE in result.applied
    assert result.backup_path is not None and pathlib.Path(result.backup_path).is_file()
    assert _dump(db) == before
    assert tdb.current_schema_version(db) >= FENCE


def test_a_second_run_is_a_no_op(tmp_path):
    db = _db_at_2_3(tmp_path)
    tdb.migrate(db)
    again = tdb.migrate(db)
    assert again.applied == [] and again.backup_path is None
