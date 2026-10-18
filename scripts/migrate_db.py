#!/usr/bin/env python3
"""Migrate the pipeline database to the latest schema.

Thin wrapper over tubematic_core.db.migrate() — see that module for why every
process is safe to call it (a run with nothing pending is one cheap SELECT;
a run with something pending holds a write lock so concurrent callers never
double-apply a migration).

Run from the repo root:
    python scripts/migrate_db.py [--db PATH] [--allow-no-backup]
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from onboard.config import DB_PATH  # noqa: E402
from tubematic_core.db import MigrationError, migrate  # noqa: E402


def warn(msg: str) -> None:
    print(f"  \033[33m!\033[0m  {msg}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default=str(DB_PATH),
        help="Path to the database (default: %(default)s)")
    parser.add_argument(
        "--allow-no-backup", action="store_true",
        help="Skip the pre-migration backup. Not recommended.")
    args = parser.parse_args(argv)

    if args.allow_no_backup:
        # A relaxed safety guarantee must be visible, not silent — same rule
        # onboarding follows for --disable-verification.
        warn("--allow-no-backup: migrating with NO pre-migration backup. "
             "If this migration fails or does the wrong thing, there is no "
             "snapshot to restore from.")

    try:
        result = migrate(args.db, backup=not args.allow_no_backup)
    except MigrationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not result.applied:
        print(f"Already current at schema version {result.to_version:04d}.")
        return 0

    applied = ", ".join(f"{v:04d}" for v in result.applied)
    print(f"Migrated {result.from_version:04d} -> {result.to_version:04d} "
          f"(applied: {applied})")
    if result.backup_path:
        print(f"Backup written: {result.backup_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
