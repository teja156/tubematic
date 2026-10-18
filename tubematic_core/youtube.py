"""YouTube video URLs for the mining strategy: one rule for what is accepted.

A mining URL is handed to Gemini as `file_data.file_uri`, a paid call. Before
this module nothing checked that it was a YouTube video at all — any string,
`file://` or an internal address included, reached the request. So every
writer (POST /research/mining-sources, MCP set_mining_sources) and the one
reader that spends (MCP mine_youtube_topics) goes through check_mining_sources.

Accepted, on youtube.com, www.youtube.com and m.youtube.com, http or https:
  /watch?v=ID (v may follow other query parameters), /shorts/ID, /live/ID,
and https?://youtu.be/ID. The id is exactly 11 characters of [A-Za-z0-9_-].
Every accepted form is rewritten to https://www.youtube.com/watch?v=ID, so a
query tail (?si=..., &t=30) never reaches Gemini and two spellings of one video
deduplicate.

The host is anchored by the "/" that must follow it, which is what rejects
userinfo (youtube.com@evil), a port, and a lookalike (youtube.com.evil.com).
The input is never forwarded — only the id is — so the tail's content cannot
matter beyond being printable ASCII with no whitespace.
"""
import re

# The most URLs one install may hold as mining sources. A run makes at most
# max_mining_per_run Gemini calls whatever the list length; this bounds the
# list itself, and with it the request body every save carries.
MINING_MAX_SOURCES = 50

_ID = r"(?P<id>[A-Za-z0-9_-]{11})"
_TAIL = r"[^\s#]*"           # a query string's remainder (printable ASCII is checked first)
_FRAGMENT = r"(?:#\S*)?"
_HOST = r"(?i:https?://(?:www\.|m\.)?youtube\.com/)"
_PATTERNS = (
    re.compile(_HOST + r"watch\?(?:" + _TAIL + r"&)?v=" + _ID + r"(?:&" + _TAIL + r")?" + _FRAGMENT),
    re.compile(_HOST + r"(?:shorts|live)/" + _ID + r"(?:\?" + _TAIL + r")?" + _FRAGMENT),
    re.compile(r"(?i:https?://youtu\.be/)" + _ID + r"(?:\?" + _TAIL + r")?" + _FRAGMENT),
)

ACCEPTED_FORMS = ("https://www.youtube.com/watch?v=<id>, https://youtu.be/<id>, "
                  "https://www.youtube.com/shorts/<id> or https://www.youtube.com/live/<id>, "
                  "with an 11-character video id")

# How much of a refused entry an error message quotes.
_QUOTE_CHARS = 120


def canonical_youtube_url(value) -> str | None:
    """https://www.youtube.com/watch?v=ID for an accepted YouTube video URL, else None."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    # isascii + isprintable together rule out every control character
    # (newline, tab, NUL) and anything non-ASCII before a pattern is tried.
    if not text or not text.isascii() or not text.isprintable():
        return None
    for pattern in _PATTERNS:
        match = pattern.fullmatch(text)
        if match:
            return f"https://www.youtube.com/watch?v={match['id']}"
    return None


def canonical_youtube_urls(values) -> tuple[list, list]:
    """(the accepted entries canonicalised, first occurrence kept; the refused entries)."""
    urls, bad = [], []
    for value in values:
        url = canonical_youtube_url(value)
        if url is None:
            bad.append(value)
        elif url not in urls:
            urls.append(url)
    return urls, bad


def _quote(value) -> str:
    text = repr(value)
    return text if len(text) <= _QUOTE_CHARS else text[:_QUOTE_CHARS] + "…"


def check_mining_sources(values) -> tuple[list | None, str | None]:
    """(canonical list, None) for a usable list of mining sources, else (None, error).

    The whole list is refused if any entry is not an accepted YouTube video
    URL, naming every one that is not, so nothing is silently dropped. An
    empty list is valid here — it clears the sources; a caller that needs at
    least one URL checks that itself.
    """
    if not isinstance(values, list):
        return None, "youtube_urls must be a list"
    urls, bad = canonical_youtube_urls(values)
    if bad:
        return None, ("Not a YouTube video URL: " + ", ".join(_quote(v) for v in bad)
                      + f". Accepted forms: {ACCEPTED_FORMS}.")
    if len(urls) > MINING_MAX_SOURCES:
        return None, (f"Too many mining sources: {len(urls)} distinct videos, "
                      f"at most {MINING_MAX_SOURCES}.")
    return urls, None
