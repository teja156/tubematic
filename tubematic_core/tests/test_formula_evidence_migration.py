"""The 0028 migration (TMDEV-217): videos.formula_evidence, what the install's
watch figures said when the video's formula was picked.

No backfill: '' means the pick was made without evidence, which is true of
every pick made before the upgrade. What matters is that an existing pick, its
reason and its script are kept as they are, and that a re-run is a no-op.
"""
import pathlib
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402

KEPT = ("status", "script", "formula_id", "formula_pick", "formula_runner_up", "formula_reason")


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_before_0028(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_before_0028"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version < 28:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, script, formula_id, formula_pick, "
                "formula_runner_up, formula_reason, created_at, updated_at) VALUES "
                "('picked', 't', 'SCRIPT_READY', 'One. Two.', 'scene-story', 'scene-story', "
                "'follow-the-flow', 'A true case.', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    return db


def _rows(db, cols) -> dict:
    con = sqlite3.connect(db)
    out = {r[0]: tuple(r[1:]) for r in con.execute(f"SELECT id, {', '.join(cols)} FROM videos")}
    con.close()
    return out


def test_an_existing_pick_is_kept_and_has_no_evidence(tmp_path):
    db = _db_before_0028(tmp_path)
    before = _rows(db, KEPT)
    tdb.migrate(db)
    tdb.migrate(db)  # every process migrates on start; a second run is a no-op
    assert _rows(db, KEPT) == before
    assert _rows(db, ("formula_evidence",)) == {"picked": ("",)}


def test_a_new_video_starts_with_no_evidence(tmp_path):
    db = _db_before_0028(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) VALUES "
                "('new', 't', 'TOPIC_PROPOSED', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    assert _rows(db, ("formula_evidence",))["new"] == ("",)
