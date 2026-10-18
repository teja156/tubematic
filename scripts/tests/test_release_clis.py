"""Unit tests for the three release-tooling host CLIs (TMDEV-91 Phase 2):
print_version.py, migrate_db.py, backup_db.py.

Each is a thin wrapper over tubematic_core — these tests pin the CLI-level
contract (exit codes, what gets printed where, and that --allow-no-backup's
relaxed safety guarantee is visible, not silent), not tubematic_core's own
migration logic, which is covered by tubematic_core/tests.

TUBEMATIC_BACKUPS_DIR is set in every test that can write a backup so none
of them ever touch a real backups directory.
"""
import os
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, REPO_ROOT)

from tubematic_core.version import version as core_version  # noqa: E402

import backup_db  # noqa: E402
import migrate_db  # noqa: E402
import print_version  # noqa: E402


def _legacy_db(path):
    """An on-disk sqlite file with no schema_migrations table at all — the
    same shape as a pre-migration database. current_schema_version() reads
    this as version 0, so every migration is pending."""
    con = sqlite3.connect(str(path))
    con.execute("CREATE TABLE placeholder (id INTEGER)")
    con.commit()
    con.close()


# ── print_version.py ────────────────────────────────────────────────────────

def test_print_version_matches_the_version_file(capsys):
    rc = print_version.main([])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.strip() == core_version()


# ── migrate_db.py ────────────────────────────────────────────────────────────

def test_migrate_db_reports_nothing_to_do_on_a_current_database(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))
    db = tmp_path / "tubematic.db"
    _legacy_db(db)

    # Bring it current first, outside the CLI under test.
    from tubematic_core.db import migrate
    migrate(db)
    capsys.readouterr()  # discard setup noise, if any
    backups_before = list(Path(tmp_path / "backups").glob("*")) if (tmp_path / "backups").exists() else []

    rc = migrate_db.main(["--db", str(db)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Already current" in out
    # A no-op run must not grow the backup directory any further.
    backups_after = list(Path(tmp_path / "backups").glob("*")) if (tmp_path / "backups").exists() else []
    assert backups_after == backups_before


def test_migrate_db_applies_and_reports_the_backup_path(tmp_path, monkeypatch, capsys):
    backups_dir = tmp_path / "backups"
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(backups_dir))
    db = tmp_path / "tubematic.db"
    _legacy_db(db)

    rc = migrate_db.main(["--db", str(db)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "0000" in out and "0001" in out
    assert "Backup written:" in out
    backups = list(backups_dir.iterdir())
    assert len(backups) == 1
    assert backups[0].exists()


def test_allow_no_backup_prints_a_visible_warning(tmp_path, monkeypatch, capsys):
    """The flag relaxes a safety guarantee, so its use must be visible in the
    output rather than silent — same rule as onboarding's --disable-verification."""
    backups_dir = tmp_path / "backups"
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(backups_dir))
    db = tmp_path / "tubematic.db"
    _legacy_db(db)

    rc = migrate_db.main(["--db", str(db), "--allow-no-backup"])
    out = capsys.readouterr().out

    assert rc == 0
    assert "--allow-no-backup" in out
    # Tied to the actual substance of the warning (no backup will exist to
    # restore from), not just any mention of "no"/"backup" — a generic
    # "flag enabled" banner with neither word missing would otherwise pass.
    assert "no pre-migration backup" in out.lower()
    # No backup should exist: the flag actually suppressed it.
    assert not backups_dir.exists() or not any(backups_dir.iterdir())


def test_migrate_db_exits_1_and_writes_the_reason_to_stderr_on_failure(tmp_path, monkeypatch, capsys):
    from tubematic_core.db import MigrationError
    from tubematic_core.db import migrate as core_migrate

    # Point the backups dir at a path that is already a regular file, so
    # backup_db()'s out_dir.mkdir() fails and migrate() raises MigrationError.
    blocker = tmp_path / "blocker"
    blocker.write_text("not a directory")
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(blocker))
    db = tmp_path / "tubematic.db"
    _legacy_db(db)

    # The expected reason comes straight from the same underlying call the
    # CLI makes, not a hardcoded guess at its wording — this call raises
    # before anything is applied (backup happens before BEGIN IMMEDIATE), so
    # re-running the identical scenario through the CLI below reproduces it
    # deterministically.
    with pytest.raises(MigrationError) as exc_info:
        core_migrate(db)
    expected_reason = str(exc_info.value)
    assert expected_reason  # sanity: the fixture actually produced a reason

    rc = migrate_db.main(["--db", str(db)])
    captured = capsys.readouterr()

    assert rc == 1
    assert captured.out == "" or "Migrated" not in captured.out
    # Must carry the actual MigrationError text, not merely be non-empty —
    # a regression that swapped in a generic "migration failed" message
    # would otherwise pass unchanged.
    assert expected_reason in captured.err


# ── backup_db.py ─────────────────────────────────────────────────────────────

def test_backup_db_writes_a_backup_and_prints_the_path(tmp_path, monkeypatch, capsys):
    backups_dir = tmp_path / "backups"
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(backups_dir))
    db = tmp_path / "tubematic.db"
    _legacy_db(db)

    rc = backup_db.main(["--db", str(db)])
    out = capsys.readouterr().out

    assert rc == 0
    assert "Backup written:" in out
    backups = list(backups_dir.iterdir())
    assert len(backups) == 1


def test_backup_db_exits_1_when_the_database_does_not_exist(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("TUBEMATIC_BACKUPS_DIR", str(tmp_path / "backups"))
    missing = tmp_path / "nope.db"

    rc = backup_db.main(["--db", str(missing)])
    captured = capsys.readouterr()

    assert rc == 1
    assert "does not exist" in captured.err
