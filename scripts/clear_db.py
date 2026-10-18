#!/usr/bin/env python3
"""Interactive database reset tool.

Provides surgical options for clearing pipeline state without having to
delete the entire database file. Useful during development and testing.

Options:
  1. Delete a single video (and its comments)
  2. Delete all videos in a project
  3. Reset a video to an earlier status (for re-processing)
  4. Wipe all videos (keep schema)
  5. Full reset — drop and recreate all tables

Run from scripts/:
    python clear_db.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))  # repo root, for tubematic_core

from config import DB_FILE  # noqa: E402
import sqlite3
import textwrap


# Minimal DB helpers (db.py was moved to mcp/server.py)
def _db_con():
    con = sqlite3.connect(str(DB_FILE))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

class db:  # noqa: N801
    @staticmethod
    def init_db():
        from tubematic_core import db as tdb
        tdb.migrate(DB_FILE)

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
    def list_projects():
        con = _db_con()
        rows = con.execute("SELECT * FROM projects ORDER BY created_at DESC").fetchall()
        con.close()
        return [dict(r) for r in rows]

    @staticmethod
    def set_video_status(video_id, new_status):
        con = _db_con()
        con.execute("UPDATE videos SET status = ? WHERE id = ?", (new_status, video_id))
        con.commit()
        con.close()


# ── Helpers ────────────────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"


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


def _raw_exec(sql: str, params: tuple = ()) -> None:
    con = sqlite3.connect(DB_FILE)
    con.execute("PRAGMA foreign_keys=ON")
    con.execute(sql, params)
    con.commit()
    con.close()


def _usage_row_count() -> int:
    """Rows in the spend ledger — which can exist with no videos at all (research
    that filed nothing, voice previews, videos deleted one by one)."""
    try:
        con = _db_con()
        n = con.execute("SELECT COUNT(*) FROM usage_events").fetchone()[0]
        con.close()
        return n
    except sqlite3.Error:
        return 0


def _recorded_spend() -> str:
    """Everything in the usage ledger, at API list prices, plus ElevenLabs credits."""
    try:
        con = _db_con()
        usd, unpriced, credits = con.execute(
            "SELECT COALESCE(SUM(cost_usd), 0), "
            "SUM(CASE WHEN cost_basis = 'unpriced' THEN 1 ELSE 0 END), "
            "COALESCE(SUM(json_extract(units, '$.credits')), 0) FROM usage_events").fetchone()
        con.close()
    except sqlite3.Error:
        return "(no usage ledger)"
    extra = f" + {unpriced} unpriced call(s)" if unpriced else ""
    return f"${usd:.2f}{extra}, {int(credits):,} ElevenLabs credits (at API list prices)"


def fmt_video(v: dict) -> str:
    topic = (v.get("topic") or "—")[:50]
    return f"{v['id'][:8]}…  [{v['status']}]  {topic}"


# ── Actions ────────────────────────────────────────────────────────────────

def delete_single_video() -> None:
    header(
        "Delete a single video",
        "Removes one video record and all its comments from the database. "
        "Does NOT delete any files in ~/.tubematic-data/jobs/ or ~/.tubematic-data/output_videos/ — "
        "use cleanup_jobs.py to remove working files.",
    )
    videos = db.list_videos()
    if not videos:
        warn("No videos in the database.")
        return

    options = [fmt_video(v) for v in videos]
    choice = pick("Which video do you want to delete?", options)
    if choice is None:
        info("Cancelled.")
        return

    idx = next(i for i, o in enumerate(options) if o == choice)
    v   = videos[idx]
    print(f"\n  Topic:  {v.get('topic')}")
    print(f"  Status: {v['status']}")
    print(f"  ID:     {v['id']}")

    if confirm(f"Permanently delete this video?", default=False):
        _raw_exec("DELETE FROM videos WHERE id = ?", (v["id"],))
        ok(f"Deleted video {v['id'][:8]}…")
    else:
        info("Cancelled.")


def delete_project_videos() -> None:
    header(
        "Delete all videos in a project",
        "Removes all video records (and comments) belonging to a project. "
        "The project record itself is also removed. "
        "Working files in ~/.tubematic-data/jobs/ are unaffected.",
    )
    projects = db.list_projects()
    if not projects:
        warn("No projects in the database.")
        return

    options = [f"{p['id'][:8]}…  {p['name']} {('— ' + p['description'][:30]) if p.get('description') else ''}" for p in projects]
    choice  = pick("Which project?", options)
    if choice is None:
        info("Cancelled.")
        return

    idx = next(i for i, o in enumerate(options) if o == choice)
    p   = projects[idx]
    vids = db.list_videos(project_id=p["id"])
    print(f"\n  Project: {p['name']}")
    print(f"  Videos:  {len(vids)}")

    if confirm(f"Delete project '{p['name']}' and all {len(vids)} video(s)?", default=False):
        _raw_exec("DELETE FROM videos WHERE project_id = ?", (p["id"],))
        _raw_exec("DELETE FROM projects WHERE id = ?", (p["id"],))
        ok(f"Deleted project '{p['name']}' and {len(vids)} video(s)")
    else:
        info("Cancelled.")


def reset_video_status() -> None:
    header(
        "Reset a video to an earlier status",
        "Moves a video back to a previous pipeline status so it can be re-processed. "
        "Useful when you want to re-run ElevenLabs, re-render, or re-review without "
        "creating a new video record. Does not modify any files on disk.",
    )

    STATUSES = [
        "TOPIC_PROPOSED", "TOPIC_APPROVED", "SCRIPT_READY",
        "VOICING", "VOICE_READY", "RENDER_QUEUED", "RENDERING", "REVISION_REQUESTED",
        "VIDEO_READY", "VIDEO_APPROVED", "PUBLISHING", "PUBLISHED",
        "TOPIC_REJECTED", "FAILED",
    ]

    videos = db.list_videos()
    if not videos:
        warn("No videos in the database.")
        return

    options = [fmt_video(v) for v in videos]
    choice  = pick("Which video do you want to reset?", options)
    if choice is None:
        info("Cancelled.")
        return

    idx = next(i for i, o in enumerate(options) if o == choice)
    v   = videos[idx]
    print(f"\n  Current status: {v['status']}")

    new_status = pick("Reset to which status?", STATUSES)
    if new_status is None:
        info("Cancelled.")
        return

    if confirm(f"Reset '{(v.get('topic') or '')[:40]}' → {new_status}?", default=False):
        db.set_video_status(v["id"], new_status)
        ok(f"Status set to {new_status}")
    else:
        info("Cancelled.")


def wipe_all_videos() -> None:
    header(
        "Wipe all videos",
        "Deletes every video and comment record from the database. "
        "Project records are also removed. The database file and schema are kept — "
        "this is equivalent to starting fresh without reinstalling. "
        "Working files in ~/.tubematic-data/jobs/ and rendered mp4s are unaffected.",
    )

    videos   = db.list_videos()
    projects = db.list_projects()

    usage_rows = _usage_row_count()
    if not videos and not usage_rows:
        warn("No videos or recorded spend in the database — nothing to wipe.")
        return

    print(f"  Videos:   {len(videos)}")
    print(f"  Projects: {len(projects)}")
    print(f"  Spend recorded: {_recorded_spend()}")
    print()
    warn("This cannot be undone.")

    if confirm("Type 'yes' to confirm wiping all videos:", default=False):
        _raw_exec("DELETE FROM comments")
        # A fresh start wipes the spend ledger too. Deleting ONE video keeps
        # its usage rows on purpose — the money was spent either way.
        _raw_exec("DELETE FROM usage_event_videos")
        _raw_exec("DELETE FROM usage_events")
        _raw_exec("DELETE FROM videos")
        _raw_exec("DELETE FROM projects")
        _raw_exec("DELETE FROM settings WHERE key = 'cursor'")
        ok(f"Wiped {len(videos)} video(s) and {len(projects)} project(s)")
    else:
        info("Cancelled.")


def full_reset() -> None:
    header(
        "Full reset — drop and recreate all tables",
        "Drops every table in the database and recreates the schema from scratch. "
        "This is the nuclear option: all videos, projects, comments, settings, and "
        "the polling cursor are permanently deleted. Use this when the schema has "
        "changed and you want a completely clean state.",
    )

    warn("This permanently destroys ALL data in the database.")
    warn("There is no undo.")
    print()

    try:
        answer = input("  Type DELETE to confirm: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit(0)

    if answer != "DELETE":
        info("Cancelled — you must type DELETE exactly.")
        return

    con = sqlite3.connect(DB_FILE)
    cur = con.cursor()
    cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cur.fetchall()]
    # Includes schema_migrations, which is what makes the recreate below a real
    # reset: leaving that table behind would produce a database claiming to be
    # fully migrated while holding no tables, and the next migrate() would apply
    # nothing at all.
    for table in tables:
        con.execute(f"DROP TABLE IF EXISTS {table}")
    con.commit()
    con.close()

    db.init_db()
    ok(f"Dropped {len(tables)} table(s) and recreated schema")


# ── Main menu ──────────────────────────────────────────────────────────────

MENU_OPTIONS = [
    ("Delete a single video",                delete_single_video),
    ("Delete all videos in a project",       delete_project_videos),
    ("Reset a video to an earlier status",   reset_video_status),
    ("Wipe all videos (keep schema)",        wipe_all_videos),
    ("Full reset — drop and recreate all tables", full_reset),
]


def main() -> None:
    print(f"\n{BOLD}  Tubematic — Database Reset Tool{RESET}")
    print(f"  {DIM}DB: {DB_FILE}{RESET}")
    print(f"\n  {YELLOW}All destructive operations ask for confirmation before executing.{RESET}")

    db.init_db()

    while True:
        print(f"\n{'─' * 55}")
        print("  What would you like to do?")
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
            else:
                warn("Invalid choice.")
        except ValueError:
            warn("Enter a number.")


if __name__ == "__main__":
    main()
