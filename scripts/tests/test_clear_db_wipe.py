"""clear_db.py's "Wipe all videos" also clears the spend ledger (TMDEV-107).

An install can hold recorded spend and no videos at all — research that filed
nothing, voice previews, videos deleted one by one. The wipe used to bail out
on "no videos" before reaching the ledger, so a fresh start could not clear
recorded spend short of the destructive full reset.
"""
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import clear_db  # noqa: E402
from tubematic_core import db as tdb  # noqa: E402
from tubematic_core import usage as tusage  # noqa: E402


def _ledger_rows(db_file):
    con = sqlite3.connect(db_file)
    n = con.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
    con.close()
    return n


def test_the_wipe_clears_a_ledger_with_no_videos(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))
    db_file = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db_file)
    monkeypatch.setattr(clear_db, "DB_FILE", db_file)
    monkeypatch.setattr(clear_db, "confirm", lambda *a, **kw: True)
    tusage.record_usage(db_file, service="elevenlabs", model="eleven_v3",
                        operation="voice_preview", units={"credits": 90})
    assert _ledger_rows(db_file) == 1

    clear_db.wipe_all_videos()

    assert _ledger_rows(db_file) == 0


def test_an_empty_database_still_has_nothing_to_wipe(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))
    db_file = tmp_path / "data" / "tubematic.db"
    tdb.migrate(db_file)
    monkeypatch.setattr(clear_db, "DB_FILE", db_file)
    monkeypatch.setattr(clear_db, "confirm", lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("must not ask to confirm a no-op")))
    clear_db.wipe_all_videos()
    assert "nothing to wipe" in capsys.readouterr().out
