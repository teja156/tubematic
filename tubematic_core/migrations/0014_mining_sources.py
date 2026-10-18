"""0014 — stored mining sources must be YouTube video URLs (TMDEV-160).

Mining hands each stored URL to Gemini as file_data.file_uri, and nothing used
to check that one was a YouTube video. The writers now refuse a list with any
entry that is not, and store each in one canonical form. This migration brings
an existing list to the same shape:

- an accepted URL is rewritten to https://www.youtube.com/watch?v=<id>;
- two spellings of one video are kept once, at the first's position;
- anything else is DROPPED, and each dropped entry is logged at WARNING;
- past 50 distinct videos, the rest are dropped and logged the same way.

Dropping is the user's decision, and it is what keeps the dashboard usable: it
re-sends the whole list on every add and remove, so one legacy invalid entry
would make every later save fail. The automatic pre-migration backup holds the
list as it was.

The log is the logging module's, under the logger "tubematic.migrations".
Whichever service migrates first (normally tubematic-api, at start) writes it
to its own output, so `docker compose logs` shows it. That line and the
backup are the only record of what was dropped.

A row that is not a JSON list is replaced by [] and its value logged: every
reader would otherwise hand it to a writer that refuses it. A missing row is
left alone (a fresh database, or sources never configured).

The rule is copied here rather than imported from tubematic_core.youtube on
purpose: a shipped migration must do the same thing forever.

*** THIS FILE HAS SHIPPED ONCE MERGED. DO NOT EDIT IT. ***
"""
import json
import logging
import re

log = logging.getLogger("tubematic.migrations")

_MAX_SOURCES = 50
_ID = r"(?P<id>[A-Za-z0-9_-]{11})"
_TAIL = r"[^\s#]*"
_FRAGMENT = r"(?:#\S*)?"
_HOST = r"(?i:https?://(?:www\.|m\.)?youtube\.com/)"
_PATTERNS = (
    re.compile(_HOST + r"watch\?(?:" + _TAIL + r"&)?v=" + _ID + r"(?:&" + _TAIL + r")?" + _FRAGMENT),
    re.compile(_HOST + r"(?:shorts|live)/" + _ID + r"(?:\?" + _TAIL + r")?" + _FRAGMENT),
    re.compile(r"(?i:https?://youtu\.be/)" + _ID + r"(?:\?" + _TAIL + r")?" + _FRAGMENT),
)


def _canonical(value):
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or not text.isascii() or not text.isprintable():
        return None
    for pattern in _PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return f"https://www.youtube.com/watch?v={match['id']}"
    return None


def _clip(value) -> str:
    text = repr(value)
    return text if len(text) <= 200 else text[:200] + "…"


def up(con):
    row = con.execute(
        "SELECT value FROM settings WHERE key = 'mining_youtube_urls'").fetchone()
    if row is None:
        return
    try:
        stored = json.loads(row[0])
    except (TypeError, ValueError):
        stored = None
    if not isinstance(stored, list):
        log.warning("Migration 0014 cleared the mining sources: the stored value was not a "
                    "list of URLs: %s", _clip(row[0]))
        con.execute("UPDATE settings SET value = '[]' WHERE key = 'mining_youtube_urls'")
        return

    kept, invalid, over_cap = [], [], []
    for value in stored:
        url = _canonical(value)
        if url is None:
            invalid.append(value)
        elif url in kept:
            continue
        elif len(kept) >= _MAX_SOURCES:
            over_cap.append(value)
        else:
            kept.append(url)

    if invalid:
        log.warning("Migration 0014 dropped %d mining source(s) that are not YouTube video "
                    "URLs: %s", len(invalid), ", ".join(_clip(v) for v in invalid))
    if over_cap:
        log.warning("Migration 0014 dropped %d mining source(s) past the limit of %d: %s",
                    len(over_cap), _MAX_SOURCES, ", ".join(_clip(v) for v in over_cap))
    value = json.dumps(kept)
    if value != row[0]:
        con.execute("UPDATE settings SET value = ? WHERE key = 'mining_youtube_urls'", (value,))
