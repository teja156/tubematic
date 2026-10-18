#!/usr/bin/env python3
"""Pipeline status overview.

Shows a live snapshot of everything in the Tubematic pipeline:
  - Video counts by status
  - Recent videos with their topic, status, and cost
  - Total spend across all videos
  - API + MCP container health

Run from scripts/:
    python status.py

Or from the repo root:
    python scripts/status.py
"""
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running from repo root or scripts/
sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import sqlite3 as _sqlite3  # noqa: E402
from config import RENDERER_URL, MCP_URL, DB_FILE, DATA_ROOT  # noqa: E402
from tubematic_core import usage as tusage  # noqa: E402


def _local_date(iso_utc: str) -> str:
    """Parse a UTC ISO timestamp (...Z) and return its host-local calendar date
    (YYYY-MM-DD). A raw [:10] string slice of the UTC value prints the wrong
    day for any evening-local timestamp."""
    if not iso_utc:
        return ""
    try:
        dt = datetime.fromisoformat(iso_utc.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d")
    except ValueError:
        return iso_utc[:10]


# Minimal read-only DB helpers (db.py was moved to mcp/server.py)
def _db_init():
    DB_FILE.parent.mkdir(parents=True, exist_ok=True)
    con = _sqlite3.connect(str(DB_FILE))
    con.execute("PRAGMA journal_mode=WAL")
    con.row_factory = _sqlite3.Row
    return con

class db:  # noqa: N801
    @staticmethod
    def init_db():
        con = _db_init()
        con.close()

    @staticmethod
    def list_videos(status=None, project_id=None):
        con = _db_init()
        clauses, params = [], []
        if status:
            clauses.append("status = ?"); params.append(status)
        if project_id:
            clauses.append("project_id = ?"); params.append(project_id)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        rows = con.execute(f"SELECT * FROM videos {where} ORDER BY created_at DESC", params).fetchall()
        con.close()
        return [dict(r) for r in rows]

try:
    import httpx
    _HAS_HTTPX = True
except ImportError:
    _HAS_HTTPX = False


# ── Formatting helpers ─────────────────────────────────────────────────────

RESET  = "\033[0m"
BOLD   = "\033[1m"
DIM    = "\033[2m"
GREEN  = "\033[32m"
YELLOW = "\033[33m"
RED    = "\033[31m"
CYAN   = "\033[36m"
WHITE  = "\033[37m"

STATUS_COLORS = {
    "TOPIC_PROPOSED":    CYAN,
    "TOPIC_APPROVED":    CYAN,
    "TOPIC_REJECTED":    RED + DIM,
    "SCRIPT_READY":      YELLOW,
    "VOICING":           YELLOW,
    "VOICE_READY":       YELLOW,
    "RENDER_QUEUED":     YELLOW,
    "RENDERING":         YELLOW,
    "REVISION_REQUESTED": RED,
    "VIDEO_READY":       GREEN,
    "VIDEO_APPROVED":    GREEN,
    "SCHEDULED":         GREEN,
    "PUBLISHING":        GREEN,
    "PUBLISHED":         GREEN + BOLD,
    "FAILED":            RED + BOLD,
}

HUMAN_CHECKPOINT = {"TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY"}


def colored_status(status: str) -> str:
    color = STATUS_COLORS.get(status, WHITE)
    marker = " ⏳" if status in HUMAN_CHECKPOINT else ""
    return f"{color}{status}{RESET}{marker}"


def fmt_usd(usd: float) -> str:
    if not usd:
        return f"{DIM}$0.00{RESET}"
    if usd < 0.01:
        return "<$0.01"
    return f"${usd:.2f}"


def truncate(s: str, n: int) -> str:
    return s if len(s) <= n else s[:n - 1] + "…"


def divider(char: str = "─", width: int = 70) -> None:
    print(f"  {char * width}")


def section(title: str) -> None:
    print(f"\n{BOLD}  {title}{RESET}")
    divider()


# ── Sections ───────────────────────────────────────────────────────────────

def _probe(label: str, container: str, url: str) -> None:
    """Report one container's /health. Flask and MCP are separate containers
    with separate health endpoints, so either can be down while the other is
    fine — reporting them together would hide exactly that."""
    try:
        r = httpx.get(f"{url}/health", timeout=3)
        if r.status_code == 200:
            print(f"  {GREEN}✔{RESET}  {container}  {GREEN}healthy{RESET}  ({url})")
        else:
            print(f"  {YELLOW}!{RESET}  {label} responded with status {r.status_code}")
    except Exception:
        print(f"  {RED}✘{RESET}  {label} unreachable at {url}")
        print(f"  {DIM}  Run: docker compose up -d {container}{RESET}")


def show_renderer_health() -> None:
    section("API + MCP")
    if not _HAS_HTTPX:
        print(f"  {DIM}httpx not installed — skipping health check{RESET}")
        return
    _probe("API", "tubematic-api", RENDERER_URL)
    _probe("MCP", "tubematic-mcp", MCP_URL)

    # The render worker has no HTTP surface of its own — the RENDER_QUEUED/
    # RENDERING counts in the pipeline summary below are the only visibility
    # into it from outside `docker compose logs tubematic-renderer`.
    queued = sum(1 for v in db.list_videos() if v["status"] in ("RENDER_QUEUED", "RENDERING"))
    if queued:
        print(f"  {YELLOW}→{RESET}  {queued} video(s) queued/rendering (tubematic-renderer worker)")


def show_status_summary() -> None:
    section("Pipeline summary")
    videos = db.list_videos()

    if not videos:
        print(f"  {DIM}No videos in the database yet.{RESET}")
        print(f"  {DIM}Run install.py to set up, then start Phase 1 work.{RESET}")
        return

    counts: dict[str, int] = {}
    for v in videos:
        counts[v["status"]] = counts.get(v["status"], 0) + 1

    # Order by pipeline stage
    ordered = [
        "TOPIC_PROPOSED", "TOPIC_APPROVED", "TOPIC_REJECTED",
        "SCRIPT_READY", "VOICING", "VOICE_READY", "RENDER_QUEUED",
        "RENDERING", "REVISION_REQUESTED", "VIDEO_READY", "VIDEO_APPROVED",
        "SCHEDULED", "PUBLISHING", "PUBLISHED", "FAILED",
    ]
    for status in ordered:
        count = counts.get(status, 0)
        if count == 0:
            continue
        checkpoint = " ← waiting for you" if status in HUMAN_CHECKPOINT else ""
        print(f"  {colored_status(status):<40}  {BOLD}{count}{RESET}{YELLOW}{checkpoint}{RESET}")

    # Any unknown statuses
    for status, count in counts.items():
        if status not in ordered:
            print(f"  {status:<40}  {count}")


def show_recent_videos(limit: int = 15) -> None:
    section(f"Recent videos (last {limit})")
    videos = db.list_videos()[:limit]

    if not videos:
        return

    tz_abbr = datetime.now().astimezone().tzname() or "local"
    header_row = f"  {'Topic':<35}  {'Status':<28}  {'Cost':>6}  Updated ({tz_abbr})"
    print(f"{DIM}{header_row}{RESET}")
    divider("·")

    con = _db_init()
    try:
        for v in videos:
            topic    = truncate(v.get("topic") or "—", 35)
            status   = colored_status(v["status"])
            try:
                costs = tusage.video_costs(con, v["id"])
                cost  = fmt_usd(costs["total_usd"]) if costs["has_usage"] else f"{DIM}—{RESET}"
            except _sqlite3.Error:
                cost  = f"{DIM}—{RESET}"
            updated  = _local_date(v.get("updated_at") or "")
            print(f"  {topic:<35}  {status:<40}  {cost:>6}  {DIM}{updated}{RESET}")
    finally:
        con.close()


def show_cost_summary() -> None:
    """This month's spend from the usage ledger (tubematic_core/usage.py)."""
    section("Spend this month")
    since = datetime.now(timezone.utc).strftime("%Y-%m-01T00:00:00Z")
    con = _db_init()
    try:
        spend = tusage.spend_summary(con, since)
    except _sqlite3.Error:
        print(f"  {DIM}No usage ledger yet — start the stack once so the database migrates.{RESET}")
        return
    finally:
        con.close()

    print(f"  Videos ({spend['video_count']})          {fmt_usd(spend['videos']):>8}")
    print(f"  Research & mining   {fmt_usd(spend['research']):>8}")
    print(f"  Other agent runs    {fmt_usd(spend['agent_other'] + spend['other']):>8}")
    divider("·", 30)
    print(f"  {BOLD}Total               {fmt_usd(spend['total_usd']):>8}{RESET}")
    if spend["unpriced_calls"]:
        print(f"  {YELLOW}+ {spend['unpriced_calls']} unpriced call(s) — add a price on "
              f"Settings → Costs{RESET}")
    credits = spend["voice_credits"] + spend["preview_credits"]
    print(f"  ElevenLabs          {credits:>8,} credits")
    print(f"  {DIM}At API list prices — ignores subscriptions, plan credits and discounts.{RESET}")


def show_disk_usage() -> None:
    section("Disk usage")
    paths = {
        "~/.tubematic-data/jobs/":          DATA_ROOT / "jobs",
        "~/.tubematic-data/output_videos/": DATA_ROOT / "output_videos",
        "~/.tubematic-data/data/":          DATA_ROOT / "data",
        "transcripts/":           Path(__file__).parent.parent / "transcripts",
    }
    for label, path in paths.items():
        if not path.exists():
            print(f"  {label:<30}  {DIM}not found{RESET}")
            continue
        total = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        mb = total / (1024 * 1024)
        bar_len = min(int(mb / 5), 20)
        bar = "█" * bar_len
        print(f"  {label:<30}  {mb:6.1f}MB  {DIM}{bar}{RESET}")


def show_waiting_actions() -> None:
    """Highlight any videos currently blocked on human action."""
    waiting = []
    for status in HUMAN_CHECKPOINT:
        waiting.extend(db.list_videos(status=status))

    if not waiting:
        return

    section("⏳ Waiting for your action")
    for v in waiting:
        topic = truncate(v.get("topic") or "—", 45)
        print(f"  {colored_status(v['status'])}  —  {topic}")
    print()


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    print(f"\n{BOLD}  Tubematic — Pipeline Status{RESET}")
    print(f"  {DIM}DB: {DB_FILE}{RESET}")

    db.init_db()

    show_renderer_health()
    show_waiting_actions()
    show_status_summary()
    show_recent_videos()
    show_cost_summary()
    show_disk_usage()
    print()


if __name__ == "__main__":
    main()
