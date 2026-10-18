#!/usr/bin/env python3
"""Job working file cleanup tool.

~/.tubematic-data/jobs/ accumulates per-video working files (audio.mp3, timeline.json,
scene-config.json) over time. This tool helps you reclaim disk space by
removing job directories that are no longer needed.

The render worker's retention sweep (settings.retention_days) already deletes
both the job directory *and* the rendered mp4 of every PUBLISHED video once it
has been published for that many days, and archives the row; with
settings.unpublished_retention_days set, it does the same to FAILED and
TOPIC_REJECTED videos. This tool is the
manual, earlier, job-dir-only complement: mode 1 frees a published video's
working files while keeping its mp4 playable.

Cleanup modes:
  1. Remove jobs for PUBLISHED videos      (safest — video is live)
  2. Remove jobs for VIDEO_READY videos    (video is approved but not yet uploaded)
  3. Remove orphaned jobs                  (directory exists but no DB record)
  4. Remove a specific job directory
  5. Remove ALL job directories            (nuclear option)

Run from scripts/:
    python cleanup_jobs.py
"""
import shutil
import sys
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from config import JOBS_DIR, DB_FILE  # noqa: E402
import sqlite3 as _sqlite3


# Minimal DB helpers (db.py was moved to mcp/server.py)
def _db_con():
    con = _sqlite3.connect(str(DB_FILE))
    con.row_factory = _sqlite3.Row
    return con

class db:  # noqa: N801
    @staticmethod
    def init_db():
        pass

    @staticmethod
    def list_videos(status=None, project_id=None):
        con = _db_con()
        clauses, params = [], []
        if status:
            clauses.append("status = ?"); params.append(status)
        if project_id:
            clauses.append("project_id = ?"); params.append(project_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = con.execute(f"SELECT * FROM videos {where} ORDER BY created_at DESC", params).fetchall()
        con.close()
        return [dict(r) for r in rows]

    @staticmethod
    def get_video(video_id):
        con = _db_con()
        row = con.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
        con.close()
        return dict(row) if row else None


# ── Helpers ────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"


def ok(msg: str)   -> None: print(f"  \033[32m✔\033[0m  {msg}")
def info(msg: str) -> None: print(f"  \033[34m→\033[0m  {msg}")
def warn(msg: str) -> None: print(f"  \033[33m!\033[0m  {msg}")


def header(title: str, description: str) -> None:
    print(f"\n{'═' * 60}")
    print(f"  {title}")
    print(f"{'═' * 60}")
    for line in textwrap.wrap(description, width=56):
        print(f"  {line}")
    print()


def confirm(question: str, default: bool = False) -> bool:
    suffix = "[y/N]" if not default else "[Y/n]"
    try:
        answer = input(f"  {question} {suffix} ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    if not answer:
        return default
    return answer in ("y", "yes")


def pick(prompt: str, options: list[str]) -> str | None:
    print(f"\n  {prompt}")
    for i, opt in enumerate(options, 1):
        print(f"  {DIM}{i}.{RESET} {opt}")
    print(f"  {DIM}0. Cancel{RESET}")
    try:
        raw = input("  > ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)
    if not raw or raw == "0":
        return None
    try:
        idx = int(raw) - 1
        if 0 <= idx < len(options):
            return options[idx]
    except ValueError:
        pass
    return None


def dir_size_mb(path: Path) -> float:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file()) / (1024 * 1024)


def list_job_dirs() -> list[Path]:
    if not JOBS_DIR.exists():
        return []
    return sorted(d for d in JOBS_DIR.iterdir() if d.is_dir() and d.name != ".gitkeep")


def delete_dirs(dirs: list[Path], label: str) -> None:
    if not dirs:
        warn(f"No {label} found.")
        return

    total_mb = sum(dir_size_mb(d) for d in dirs)
    print(f"\n  {len(dirs)} director{'y' if len(dirs) == 1 else 'ies'} ({total_mb:.1f}MB):")
    for d in dirs[:10]:
        mb = dir_size_mb(d)
        files = list(d.iterdir())
        print(f"  {DIM}  {d.name:<40}  {mb:.1f}MB  ({len(files)} files){RESET}")
    if len(dirs) > 10:
        print(f"  {DIM}  … and {len(dirs) - 10} more{RESET}")

    if confirm(f"\n  Delete {len(dirs)} director{'y' if len(dirs) == 1 else 'ies'} ({total_mb:.1f}MB)?", default=False):
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)
        ok(f"Deleted {len(dirs)} director{'y' if len(dirs) == 1 else 'ies'}, freed {total_mb:.1f}MB")
    else:
        info("Cancelled.")


# ── Actions ────────────────────────────────────────────────────────────────

def cleanup_published() -> None:
    header(
        "Remove jobs for PUBLISHED videos",
        "These videos are live on YouTube. Their working files (audio.mp3, "
        "timeline.json, scene-config.json) are no longer needed. The rendered "
        "mp4 in ~/.tubematic-data/output_videos/ is kept — only the intermediate working "
        "files in ~/.tubematic-data/jobs/ are removed. (The retention sweep does this "
        "automatically, mp4 included, retention_days after a video is published.)",
    )
    published = db.list_videos(status="PUBLISHED")
    job_dirs  = list_job_dirs()
    job_names = {d.name for d in job_dirs}

    # Match by video_id (job dirs are named by video_id or job_id)
    targets = []
    for v in published:
        vid = v["id"]
        # Job dir may be named by video_id or a UUID job submitted for that video
        matches = [d for d in job_dirs if d.name == vid or d.name.startswith(vid[:8])]
        targets.extend(matches)

    delete_dirs(targets, "job directories for PUBLISHED videos")


def cleanup_video_ready() -> None:
    header(
        "Remove jobs for VIDEO_READY videos",
        "These videos have been rendered and reviewed but not yet uploaded. "
        "Removing their working files is safe — you can re-render from the "
        "scene-config if needed, but you'd need to re-run ElevenLabs again. "
        "Only do this if you are sure you won't need to re-render.",
    )
    ready    = db.list_videos(status="VIDEO_READY")
    job_dirs = list_job_dirs()

    targets = []
    for v in ready:
        vid = v["id"]
        matches = [d for d in job_dirs if d.name == vid or d.name.startswith(vid[:8])]
        targets.extend(matches)

    delete_dirs(targets, "job directories for VIDEO_READY videos")


def cleanup_orphaned() -> None:
    header(
        "Remove orphaned job directories",
        "An orphaned job directory exists on disk but has no corresponding "
        "video record in the database. This happens when a render was submitted "
        "manually or when a video was deleted from the DB without cleaning up files. "
        "These directories serve no purpose and can be safely removed.",
    )
    job_dirs = list_job_dirs()
    if not job_dirs:
        warn("No job directories found.")
        return

    all_videos   = db.list_videos()
    known_ids    = {v["id"] for v in all_videos}
    orphaned     = [d for d in job_dirs if d.name not in known_ids]

    delete_dirs(orphaned, "orphaned job directories")


def cleanup_specific() -> None:
    header(
        "Remove a specific job directory",
        "Choose a single job directory to delete. Useful for cleaning up a "
        "test render or a failed job without touching anything else.",
    )
    job_dirs = list_job_dirs()
    if not job_dirs:
        warn("No job directories found in ~/.tubematic-data/jobs/")
        return

    options = []
    for d in job_dirs:
        mb    = dir_size_mb(d)
        files = len(list(d.iterdir()))
        v     = db.get_video(d.name)
        label = f"{d.name}  ({mb:.1f}MB, {files} files)"
        if v:
            label += f"  [{v['status']}] {(v.get('topic') or '')[:30]}"
        else:
            label += "  [no DB record]"
        options.append(label)

    choice = pick("Which directory?", options)
    if choice is None:
        info("Cancelled.")
        return

    idx = next(i for i, o in enumerate(options) if o == choice)
    d   = job_dirs[idx]
    mb  = dir_size_mb(d)

    if confirm(f"Delete {d.name} ({mb:.1f}MB)?", default=False):
        shutil.rmtree(d, ignore_errors=True)
        ok(f"Deleted {d.name} ({mb:.1f}MB freed)")
    else:
        info("Cancelled.")


def cleanup_all() -> None:
    header(
        "Remove ALL job directories",
        "Deletes every directory in ~/.tubematic-data/jobs/. This frees the most disk "
        "space but means you cannot re-render any existing video without "
        "re-running ElevenLabs first. Rendered mp4s in ~/.tubematic-data/output_videos/ "
        "are NOT touched.",
    )
    job_dirs = list_job_dirs()
    if not job_dirs:
        warn("No job directories found.")
        return

    total_mb = sum(dir_size_mb(d) for d in job_dirs)
    warn(f"This will delete ALL {len(job_dirs)} job director{'y' if len(job_dirs) == 1 else 'ies'} ({total_mb:.1f}MB).")
    warn("Re-rendering any video will require re-running ElevenLabs.")

    try:
        answer = input("\n  Type DELETE to confirm: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

    if answer != "DELETE":
        info("Cancelled — you must type DELETE exactly.")
        return

    for d in job_dirs:
        shutil.rmtree(d, ignore_errors=True)
    (JOBS_DIR / ".gitkeep").touch()
    ok(f"Deleted {len(job_dirs)} director{'y' if len(job_dirs) == 1 else 'ies'}, freed {total_mb:.1f}MB")


# ── Main menu ──────────────────────────────────────────────────────────────

MENU_OPTIONS = [
    ("Remove jobs for PUBLISHED videos (safest)",      cleanup_published),
    ("Remove jobs for VIDEO_READY videos",             cleanup_video_ready),
    ("Remove orphaned job directories (no DB record)", cleanup_orphaned),
    ("Remove a specific job directory",                cleanup_specific),
    ("Remove ALL job directories",                     cleanup_all),
]


def show_disk_summary() -> None:
    job_dirs = list_job_dirs()
    if not job_dirs:
        print(f"  {DIM}~/.tubematic-data/jobs/ is empty.{RESET}")
        return
    total_mb = sum(dir_size_mb(d) for d in job_dirs)
    print(f"  {len(job_dirs)} job director{'y' if len(job_dirs) == 1 else 'ies'}  —  {total_mb:.1f}MB total in ~/.tubematic-data/jobs/")


def main() -> None:
    print(f"\n{BOLD}  Tubematic — Job Cleanup{RESET}")
    print(f"  {DIM}Jobs directory: {JOBS_DIR}{RESET}\n")
    db.init_db()
    show_disk_summary()

    while True:
        print(f"\n{'─' * 55}")
        print("  What would you like to clean up?")
        print()
        for i, (label, _) in enumerate(MENU_OPTIONS, 1):
            print(f"  {DIM}{i}.{RESET} {label}")
        print(f"  {DIM}0. Exit{RESET}")

        try:
            raw = input("\n  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  Bye.")
            sys.exit(0)

        if raw == "0" or raw == "":
            print("  Bye.")
            sys.exit(0)

        try:
            idx = int(raw) - 1
            if 0 <= idx < len(MENU_OPTIONS):
                MENU_OPTIONS[idx][1]()
                show_disk_summary()
            else:
                warn("Invalid choice.")
        except ValueError:
            warn("Enter a number.")


if __name__ == "__main__":
    main()
