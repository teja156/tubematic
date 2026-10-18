"""Shared configuration for the cron/CLI scripts (poll.py, status.py).

All pipeline-execution constants (ElevenLabs, Gemini, DB path, etc.) live in
mcp/server.py, which is the single owner of those concerns.

Since TMDEV-73 there is no .env: the settings table is the source of truth.
The scheduling values that used to live here now reach poll.py on argv (the
workspace path and agent binary, which it needs before it can call the API)
or over HTTP (everything else). Deliberately no DB access in this module —
poll.py imports it, and "poll.py needs no DB imports" is a documented
invariant (renderer/api/pipeline.py::get_pipeline_status). A host script that
needs the DB reads it itself.
"""
import os
import re
from datetime import datetime
from pathlib import Path

# ── Paths ───────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent

# Host-side data root — fixed, not configurable (TMDEV-76).
# The pipeline database (which holds the API keys) and the rendered video
# library are machine state, not properties of a git checkout: under the old
# repo-relative `mounted/` a `rm -rf` + re-clone destroyed both silently.
# Keep in sync with docker-compose.yml's volume devices, onboard/config.py,
# scripts/config.py, mcp/server.py and uninstall.py.
DATA_ROOT = Path.home() / ".tubematic-data"
JOBS_DIR    = DATA_ROOT / "jobs"
DB_FILE     = DATA_ROOT / "data" / "tubematic.db"

# ── Renderer / Flask API ────────────────────────────────────────────────────
# Everything runs on one machine and compose publishes a fixed port, so this
# was never really configurable. Kept as an env read purely as a power-user
# escape hatch; onboarding no longer writes it anywhere.
RENDERER_URL = os.getenv("RENDERER_URL", "http://localhost:4000")

# ── MCP ─────────────────────────────────────────────────────────────────────
# Its own container (tubematic-mcp) since the Flask/MCP split, so it has a
# health endpoint of its own and status.py reports the two separately — a
# healthy Flask no longer implies the agent's tools are reachable. Same
# escape-hatch reasoning as RENDERER_URL above.
#
# This is the server *base*, not the MCP endpoint. A trailing /mcp is stripped
# because the endpoint form is the one anybody would actually paste here: it is
# what `claude mcp add` takes and what every doc quotes. But /health is a
# FastMCP custom route served at the server root, *beside* /mcp rather than
# under it, so probing <url>/health against the endpoint form would 404 and
# report a perfectly healthy MCP server as unreachable.
def _mcp_base(url: str) -> str:
    url = url.rstrip("/")
    return url[:-4] if url.endswith("/mcp") else url


MCP_URL = _mcp_base(os.getenv("MCP_URL", "http://localhost:4100"))

# ── Scheduling ──────────────────────────────────────────────────────────────
# Where poll.py writes poll.log. Fixed, not configurable: the cron line names no
# agent (TMDEV-90) — which agent runs, from which binary and workspace, is
# resolved per video over HTTP — but logging starts before the first HTTP call,
# so where to log cannot come from the API. Every agent's workspace is a
# sibling of it (~/.tubematic-agent/<agent>/), and the installer refuses one
# that contains it. Keep in sync with onboard/config.py POLL_LOG_DIR.
POLL_LOG_DIR = Path("~/.tubematic-agent/logs").expanduser()

# ── Host timezone ────────────────────────────────────────────────────────────
# Keep in sync with: renderer/api/hosttz.py host_timezone(), onboard.py host_timezone().
# Duplicated (not shared) because this runs on the host, not in a container.
# tubematic_core/ is importable from here, but it is deliberately kept to code
# whose drift between processes would be dangerous (logging, the schema, the
# service tokens) rather than being a home for anything two processes share.
_IANA_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+_-]*(?:/[A-Za-z0-9+_.-]+)*$")


def _resolve_iana_name() -> str | None:
    tz_env = os.environ.get("TZ", "").strip()
    if tz_env and _IANA_RE.match(tz_env):
        return tz_env
    try:
        with open("/etc/timezone") as f:
            for line in f:
                line = line.strip()
                if line and _IANA_RE.match(line):
                    return line
    except OSError:
        pass
    try:
        link = os.readlink("/etc/localtime")
        if "/zoneinfo/" in link:
            name = link.split("/zoneinfo/", 1)[1]
            if _IANA_RE.match(name):
                return name
    except OSError:
        pass
    return None


def _label() -> str:
    """e.g. 'EDT (UTC-04:00)'. Display-only — never pass to Intl.DateTimeFormat."""
    now = datetime.now().astimezone()
    tzname = now.tzname() or "local"
    offset = now.strftime("%z")
    if offset:
        return f"{tzname} (UTC{offset[:3]}:{offset[3:]})"
    return tzname


def host_timezone() -> dict:
    """-> {"timezone": str | None, "timezone_label": str}. See renderer/api/hosttz.py
    for the full contract (IANA name or None; label is display-only)."""
    return {"timezone": _resolve_iana_name(), "timezone_label": _label()}


LOCAL_TZ_LABEL = _label()
