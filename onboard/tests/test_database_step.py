"""`apply_database` creates or migrates the pipeline database (TMDEV-91).

Onboarding is the first thing to touch a fresh database, before any container
exists, so it must produce the same schema the services expect. This used to
be a fourth hand-maintained copy of the schema (`onboard/actions.py::_SCHEMA`),
already stale by six columns and three tables. It now defers entirely to
`tubematic_core.db.migrate`.
"""
from onboard import actions
from onboard.executor import Executor, NullReporter


def _cfg():
    """apply_database does not read cfg — matches apply_renderer's tests,
    which pass None for the same reason (see test_renderer_step.py)."""
    return None


def _executor(dry_run: bool = False):
    return Executor(dry_run=dry_run)


def _reporter():
    return NullReporter()


def test_apply_database_migrates_and_stamps(tmp_path, monkeypatch):
    """Onboarding is the first thing to touch a fresh database, before any
    container exists, so it must produce the same schema the services expect."""
    import sqlite3

    db = tmp_path / "data" / "tubematic.db"
    monkeypatch.setattr(actions, "DB_PATH", db)
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))

    actions.apply_database(_cfg(), _executor(), _reporter())

    con = sqlite3.connect(db)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    stamped = con.execute("SELECT COUNT(*) FROM schema_migrations").fetchone()[0]
    con.close()
    assert {"videos", "agents", "video_publications", "settings"} <= tables
    assert stamped >= 1


def test_apply_database_does_not_write_under_dry_run(tmp_path, monkeypatch):
    db = tmp_path / "data" / "tubematic.db"
    monkeypatch.setattr(actions, "DB_PATH", db)
    actions.apply_database(_cfg(), _executor(dry_run=True), _reporter())
    assert not db.exists()
