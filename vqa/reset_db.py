#!/usr/bin/env python3
"""Reset the VQA pipeline DB back to a clean seeded state.

Regenerates ~/.tubematic-data/data/tubematic.db from scratch via make_seed_db.py's
current seed logic (not a copy of the file baked into the image at build
time, so this always reflects whatever vqa/make_seed_db.py in THIS working
tree currently specifies) — wiping every video, project, comment, and
setting back to the pristine seed (one proj_vqa project, gemini review
disabled, the default voice roster, ...).

By default also clears every file artifact a video could have left behind:
jobs/*, output_videos/*, scenes/generated/* under it — a
DB-only reset would otherwise leave those as orphaned, unreferenced disk
usage with nothing pointing at them anymore. Pass --db-only to reset just
the database and leave those in place.

Destructive and irreversible — there is no undo. Requires --yes; without
it, prints what would be deleted and changes nothing.

Usage: reset_db.py --yes [--db-only]
"""
import argparse
import shutil
import sys
from pathlib import Path

_CLEARED_SUBDIRS = ("jobs", "output_videos", "scenes/generated")


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _data_root() -> Path:
    """Where pipeline data lives — a fixed absolute path (TMDEV-76), distinct
    from the repo root above, which still locates importable source. A VQA
    session therefore reads the same tree the containers write to, wherever
    the checkout happens to sit."""
    return Path.home() / ".tubematic-data"


def _clear_dir_contents(dir_path: Path) -> list[str]:
    """Delete every entry inside dir_path, leaving dir_path itself in place.
    Returns the removed entry names, for reporting. A no-op (not an error)
    if dir_path doesn't exist."""
    if not dir_path.exists():
        return []
    removed = []
    for entry in dir_path.iterdir():
        removed.append(entry.name)
        if entry.is_dir():
            shutil.rmtree(entry)
        else:
            entry.unlink()
    return removed


def reset_db(root: Path, *, db_only: bool = False, make_seed_db=None) -> dict:
    """Perform the reset. Returns {"db_path": Path, "cleared": {subdir: [names]}}.
    make_seed_db is injectable for testing (a fake taking just an output
    path); defaults to importing the real vqa/make_seed_db.py."""
    if make_seed_db is None:
        sys.path.insert(0, str(_repo_root() / "vqa"))
        from make_seed_db import make_seed_db as make_seed_db  # noqa: E402

    db_path = root / "data" / "tubematic.db"
    make_seed_db(db_path)  # unlinks any existing db + -wal/-shm sidecars first

    cleared = {}
    if not db_only:
        for name in _CLEARED_SUBDIRS:
            cleared[name] = _clear_dir_contents(root / name)

    return {"db_path": db_path, "cleared": cleared}


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--yes", action="store_true", help="actually perform the reset (required)")
    parser.add_argument(
        "--db-only", action="store_true",
        help="reset only the database — leave jobs, output_videos, scenes/generated untouched",
    )
    args = parser.parse_args(argv)

    root = _data_root()
    db_path = root / "data" / "tubematic.db"

    if not args.yes:
        print("This would DELETE the current pipeline DB and reseed it from scratch:")
        print(f"  {db_path}")
        if not args.db_only:
            print("It would also delete every file under:")
            for name in _CLEARED_SUBDIRS:
                print(f"  {root / name}")
        print("\nThis cannot be undone. Re-run with --yes to actually do this.")
        return

    result = reset_db(root, db_only=args.db_only)
    print(f"Reset {result['db_path']}")
    for name, removed in result["cleared"].items():
        print(f"Cleared {len(removed)} item(s) from {name}/")


if __name__ == "__main__":
    main()
