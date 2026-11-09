"""The 0019 migration: the renderers, renderer_enrollments and render_timings
tables, the four lease columns on videos, and the built-in renderer's row.

Upgrading must leave every existing video unleased ('' everywhere): the
worker's lease sweep reads an empty lease on a RENDERING row as expired, which
is what re-queues a render a pre-upgrade renderer was in the middle of.
"""
import pathlib
import re
import shutil
import sqlite3
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from tubematic_core import db as tdb  # noqa: E402


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_at_0018(tmp_path) -> pathlib.Path:
    older = tmp_path / "migrations_to_0018"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 18:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO videos (id, topic, status, created_at, updated_at) "
                "VALUES ('v1', 't', 'RENDERING', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')")
    con.commit()
    con.close()
    return db


def test_existing_videos_come_out_unleased(tmp_path):
    db = _db_at_0018(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT renderer_id, render_lease_until, render_started_at, render_uploaded_at "
                       "FROM videos").fetchall() == [("", "", "", "")]
    con.close()


def test_the_builtin_renderer_row_is_seeded_enabled_and_unprobed(tmp_path):
    db = _db_at_0018(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM renderers").fetchall()
    con.close()
    assert len(rows) == 1
    r = rows[0]
    assert (r["id"], r["name"], r["builtin"], r["enabled"]) == ("builtin", "Built-in renderer", 1, 1)
    # No probe yet ('' and not verified): the GPU gates read "unknown" until the
    # renderer probes at start, never "working" from a stale value.
    assert (r["gpu_probe"], r["gpu_verified"], r["compute"], r["state"]) == ("", 0, "{}", "idle")
    assert (r["credential_hash"], r["credential_expires_at"], r["removed_at"]) == ("", "", None)
    # Stamped with the time it ran, in the database's own timestamp format.
    assert re.fullmatch(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ", r["created_at"])


def test_a_second_migrate_is_a_no_op(tmp_path):
    db = _db_at_0018(tmp_path)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("UPDATE renderers SET name = 'Renamed' WHERE id = 'builtin'")
    con.commit()
    con.close()
    tdb.migrate(db)
    con = sqlite3.connect(db)
    assert con.execute("SELECT id, name FROM renderers").fetchall() == [("builtin", "Renamed")]
    con.close()


def test_the_new_tables_take_their_documented_defaults(tmp_path):
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db)
    con = sqlite3.connect(db)
    con.execute("INSERT INTO renderers (id, name, created_at) VALUES ('r_1', 'Studio', 'x')")
    assert con.execute("SELECT builtin, enabled, credential_expires_at, previous_credential_hash "
                       "FROM renderers WHERE id = 'r_1'").fetchone() == (0, 1, "", "")
    con.execute("INSERT INTO renderer_enrollments (secret_hash, created_at, expires_at) VALUES ('h', 'a', 'b')")
    assert con.execute("SELECT name, used_at, renderer_id FROM renderer_enrollments").fetchone() == ("", None, None)
    con.execute("INSERT INTO render_timings (renderer_id, kind, on_gpu, frames, seconds, created_at) "
                "VALUES ('r_1', 'dom', 0, 10, 1.5, 'x')")
    assert con.execute("SELECT seconds FROM render_timings").fetchone() == (1.5,)
    assert con.execute("SELECT 1 FROM sqlite_master WHERE type = 'index' "
                       "AND name = 'idx_render_timings_renderer'").fetchone() == (1,)
    con.close()
