"""The spool protocol between `tubematic-mcp` and `tubematic-sandbox` (TMDEV-242).

The sandbox container has no network and mounts one thing: a spool folder it
shares with MCP. MCP writes a request there, the daemon (sandbox/daemon.py)
runs it as an unprivileged child and writes a result back. Both sides import
this module, so the limits and names cannot drift.

Layout under the spool root:

    heartbeat                 seconds since epoch, rewritten by the daemon
    req/<id>/request.json     language, code, timeout_s, inputs (aliases)
    req/<id>/in/<alias>       the input files MCP copied in
    done/<id>/result.json     what the run did (see RESULT_KEYS)
    done/<id>/out/<name>      files the code left in ./out

A request is written as `req/.<id>.tmp` and renamed, a result as
`done/.<id>.tmp` and renamed, so neither side ever reads a half-written one.
`req` and `done` are root-owned 0700: the code runs as another uid and cannot
list, read or forge any of it.

Free of the database and of I/O except the two helpers at the bottom.
"""
from __future__ import annotations

import os
import re
import time
from pathlib import Path

LANGUAGES = ("python", "javascript", "typescript")
SOURCE_NAME = {"python": "main.py", "javascript": "main.js", "typescript": "main.ts"}

MAX_CODE_BYTES = 64 * 1024
MAX_INPUT_FILES = 8
MAX_INPUT_FILE_BYTES = 12 * 1024 * 1024
MAX_INPUT_TOTAL_BYTES = 24 * 1024 * 1024
DEFAULT_TIMEOUT_S = 20
MAX_TIMEOUT_S = 60
# stdout and stderr are each cut to their first and last halves of this.
MAX_STREAM_CHARS = 8000
# A child may write this much to stdout/stderr or to one file (RLIMIT_FSIZE).
MAX_WRITE_BYTES = 16 * 1024 * 1024
MAX_OUT_FILES = 8
MAX_OUT_FILE_BYTES = 8 * 1024 * 1024
MAX_OUT_TOTAL_BYTES = 16 * 1024 * 1024
OUT_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp", ".json", ".txt", ".csv", ".svg")
IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".webp")
# How many requests may wait before MCP answers sandbox_busy.
MAX_QUEUED = 2
# The daemon rewrites the heartbeat at least this often; MCP trusts one this young.
HEARTBEAT_EVERY_S = 1.0
HEARTBEAT_MAX_AGE_S = 10.0
# A finished result nobody fetched, or a request nobody ran, is swept after this.
STALE_AFTER_S = 600

RESULT_KEYS = ("id", "exit_code", "signal", "timed_out", "output_truncated",
               "stdout", "stderr", "duration_ms", "files", "error")

NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
REQUEST_ID_RE = re.compile(r"^[0-9a-f]{16}$")


def name_ok(name) -> bool:
    return isinstance(name, str) and bool(NAME_RE.match(name)) and ".." not in name


def out_name_ok(name) -> bool:
    return name_ok(name) and name.lower().endswith(OUT_EXTENSIONS)


def cut(text: str, limit: int = MAX_STREAM_CHARS) -> tuple[str, bool]:
    """`text` cut to its first and last halves of `limit`, and whether it was cut."""
    if len(text) <= limit:
        return text, False
    half = limit // 2
    return f"{text[:half]}\n... [{len(text) - limit} characters cut] ...\n{text[-half:]}", True


def heartbeat_path(spool) -> Path:
    return Path(spool) / "heartbeat"


def write_heartbeat(spool, now: float | None = None) -> None:
    p = heartbeat_path(spool)
    tmp = p.with_name(".heartbeat.tmp")
    # 0600: the code runs as another uid and has no business in the spool, even
    # to read a timestamp.
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(repr(time.time() if now is None else now))
    tmp.replace(p)


def heartbeat_age(spool, now: float | None = None) -> float | None:
    """Seconds since the daemon last beat, or None if it never has."""
    try:
        beat = float(heartbeat_path(spool).read_text())
    except (OSError, ValueError):
        return None
    return (time.time() if now is None else now) - beat
