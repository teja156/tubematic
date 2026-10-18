"""The 0014 mining-sources migration (TMDEV-160).

The writers now refuse a list holding anything but YouTube video URLs, and the
dashboard re-sends the whole list on every change — so a legacy invalid entry
left in place would make every later save fail. The migration drops it, logs
what it dropped, and stores what it keeps in the canonical form.
"""
import json
import logging
import pathlib
import shutil
import sqlite3
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from tubematic_core import db as tdb  # noqa: E402

ID_A, ID_B = "dQw4w9WgXcQ", "abcdefghijk"


@pytest.fixture(autouse=True)
def _backups_in_tmp(tmp_path, monkeypatch):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))


def _db_at_0013(tmp_path, stored=None):
    older = tmp_path / "migrations_to_0013"
    older.mkdir()
    for mig in tdb.discover():
        if mig.version <= 13:
            shutil.copy(mig.path, older / mig.path.name)
    db = tmp_path / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    tdb.migrate(db, migrations_dir=older)
    if stored is not None:
        con = sqlite3.connect(db)
        con.execute("INSERT INTO settings (key, value) VALUES ('mining_youtube_urls', ?)",
                    (stored,))
        con.commit()
        con.close()
    return db


def _stored(db):
    con = sqlite3.connect(db)
    row = con.execute(
        "SELECT value FROM settings WHERE key = 'mining_youtube_urls'").fetchone()
    con.close()
    return row[0] if row else None


def _dropped_lines(caplog):
    return [r.getMessage() for r in caplog.records
            if r.name == "tubematic.migrations" and r.levelno == logging.WARNING]


def test_valid_urls_are_kept_in_the_canonical_form(tmp_path, caplog):
    db = _db_at_0013(tmp_path, json.dumps([f"https://youtu.be/{ID_A}?si=x",
                                           f"https://www.youtube.com/shorts/{ID_B}"]))
    with caplog.at_level(logging.WARNING):
        tdb.migrate(db)
    assert json.loads(_stored(db)) == [f"https://www.youtube.com/watch?v={ID_A}",
                                       f"https://www.youtube.com/watch?v={ID_B}"]
    assert _dropped_lines(caplog) == []


def test_invalid_entries_are_dropped_and_each_is_logged(tmp_path, caplog):
    db = _db_at_0013(tmp_path, json.dumps([
        "file:///etc/passwd", f"https://youtu.be/{ID_A}", "http://169.254.169.254/", 7,
        "https://youtu.be/tooShort"]))
    with caplog.at_level(logging.WARNING):
        tdb.migrate(db)
    assert json.loads(_stored(db)) == [f"https://www.youtube.com/watch?v={ID_A}"]
    [line] = _dropped_lines(caplog)
    assert "dropped 4 mining source(s)" in line
    for bad in ("'file:///etc/passwd'", "'http://169.254.169.254/'", "7",
                "'https://youtu.be/tooShort'"):
        assert bad in line


def test_two_spellings_of_one_video_are_kept_once(tmp_path):
    db = _db_at_0013(tmp_path, json.dumps([
        f"https://youtu.be/{ID_A}", f"https://www.youtube.com/watch?v={ID_B}",
        f"https://m.youtube.com/watch?v={ID_A}&t=30"]))
    tdb.migrate(db)
    assert json.loads(_stored(db)) == [f"https://www.youtube.com/watch?v={ID_A}",
                                       f"https://www.youtube.com/watch?v={ID_B}"]


def test_past_fifty_videos_the_rest_are_dropped_and_logged(tmp_path, caplog):
    urls = [f"https://youtu.be/{i:011d}" for i in range(52)]
    db = _db_at_0013(tmp_path, json.dumps(urls))
    with caplog.at_level(logging.WARNING):
        tdb.migrate(db)
    assert len(json.loads(_stored(db))) == 50
    [line] = _dropped_lines(caplog)
    assert "past the limit of 50" in line and urls[50] in line and urls[51] in line


def test_a_value_that_is_not_a_list_is_cleared_and_logged(tmp_path, caplog):
    db = _db_at_0013(tmp_path, "not json at all")
    with caplog.at_level(logging.WARNING):
        tdb.migrate(db)
    assert _stored(db) == "[]"
    [line] = _dropped_lines(caplog)
    assert "not json at all" in line


def test_an_empty_list_stays_empty(tmp_path, caplog):
    db = _db_at_0013(tmp_path, "[]")
    with caplog.at_level(logging.WARNING):
        tdb.migrate(db)
    assert _stored(db) == "[]"
    assert _dropped_lines(caplog) == []


def test_a_missing_row_is_left_missing(tmp_path):
    db = _db_at_0013(tmp_path)
    tdb.migrate(db)
    assert _stored(db) is None


def test_a_fresh_database_migrates(tmp_path):
    db = tmp_path / "fresh.db"
    result = tdb.migrate(db)
    assert 14 in result.applied
    assert _stored(db) is None
