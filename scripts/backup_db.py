#!/usr/bin/env python3
"""Take an unconditional backup of the pipeline database.

Thin wrapper over tubematic_core.db.backup_db() — see that module for the
online-backup-API rationale and where the file lands.

Run from the repo root:
    python scripts/backup_db.py [--db PATH]
"""
import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from onboard.config import DB_PATH  # noqa: E402
from tubematic_core.db import MigrationError, backup_db  # noqa: E402


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db", default=str(DB_PATH),
        help="Path to the database (default: %(default)s)")
    args = parser.parse_args(argv)

    try:
        backup_path = backup_db(args.db)
    except MigrationError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    print(f"Backup written: {backup_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
