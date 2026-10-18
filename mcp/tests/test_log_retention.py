"""mcp/server.py's log-retention read, which runs before the server starts.

This is configured at startup, *before* mcp.run(), so anything that escapes it
takes the whole server down before it can serve so much as /health. The two
things that go wrong are both ordinary: a database that does not exist yet (a
fresh install, or a container started before onboarding seeded it), and a
stored value that int() rejects. Neither is a reason to refuse to start.

Run from the repo root: pytest mcp/tests/test_log_retention.py
"""
import sqlite3

import pytest

import server


DEFAULT = server.LOG_RETENTION_DEFAULT_DAYS


def _db(tmp_path, value=None, *, make_table=True):
    path = tmp_path / "tubematic.db"
    con = sqlite3.connect(str(path))
    if make_table:
        con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
        if value is not None:
            con.execute("INSERT INTO settings VALUES ('log_retention_days', ?)", (value,))
    con.commit()
    con.close()
    return path


def test_a_stored_value_is_used(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", _db(tmp_path, "30"))
    assert server._log_retention_days() == 30


def test_a_missing_database_falls_back_instead_of_crashing(tmp_path, monkeypatch):
    """A fresh install, or a container that started before onboarding ran. The
    server must come up and serve /health regardless."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "does-not-exist.db")
    assert server._log_retention_days() == DEFAULT


def test_a_database_without_a_settings_table_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", _db(tmp_path, make_table=False))
    assert server._log_retention_days() == DEFAULT


def test_no_row_falls_back(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", _db(tmp_path))
    assert server._log_retention_days() == DEFAULT


@pytest.mark.parametrize("stored", ["", "abc", "14 days", "7.5", "-", "١٤"])
def test_a_malformed_value_falls_back_rather_than_raising(tmp_path, monkeypatch, stored):
    """The setting is free text in the DB. int() rejecting it must not be fatal
    — the previous form only guarded the empty string, via `or 14`."""
    monkeypatch.setattr(server, "DB_FILE", _db(tmp_path, stored))
    assert server._log_retention_days() == DEFAULT


@pytest.mark.parametrize("stored,expected", [
    ("1", 1),                                   # the floor is usable
    ("365", 365),                               # so is the ceiling
    ("0", DEFAULT),                             # would prune the file being written
    ("-5", DEFAULT),
    ("100000", DEFAULT),                        # a fat-fingered value
])
def test_out_of_range_values_fall_back(tmp_path, monkeypatch, stored, expected):
    monkeypatch.setattr(server, "DB_FILE", _db(tmp_path, stored))
    assert server._log_retention_days() == expected


def test_the_bounds_match_the_pipeline_copy():
    """Two hand-maintained copies — this module cannot import pipeline.py, since
    it runs from /app/mcp while that lives in /app/api. A cross-copy test is the
    only thing that actually holds them together; the comment never has."""
    import pathlib
    src = (pathlib.Path(__file__).resolve().parents[2]
           / "renderer" / "api" / "pipeline.py").read_text()
    for name, value in (("MIN_LOG_RETENTION_DAYS", server.MIN_LOG_RETENTION_DAYS),
                        ("MAX_LOG_RETENTION_DAYS", server.MAX_LOG_RETENTION_DAYS)):
        assert f"{name} = {value}" in src, f"{name} drifted from pipeline.py"
    assert f'"log_retention_days":     ("int",       "{DEFAULT}")' in src, \
        "the default drifted from SETTINGS_SPEC"
