"""YouTube transcript fetching for script profiles.

Lifted from the retired scripts/fetch_transcripts.py so the fetch happens
inside the API container, where the settings table (and therefore the
youtube-transcript.io key) lives. The DB is the single ingestion path now —
there is no filesystem transcript library any more.

Sequential, one video id per request: whether {"ids": [a, b, c]} returns one
item per id is unverified against the live API, and the published rate limit
(5 requests / 10s) already covers a handful of URLs per profile with known-good
request shapes.
"""
import re

import httpx

API_URL = "https://www.youtube-transcript.io/api/transcripts"

_VIDEO_ID_PATTERNS = [
    r"youtu\.be/([A-Za-z0-9_-]{11})",
    r"[?&]v=([A-Za-z0-9_-]{11})",
    r"/shorts/([A-Za-z0-9_-]{11})",
    r"/embed/([A-Za-z0-9_-]{11})",
]


def extract_video_id(url: str) -> str | None:
    """Pull the 11-character video id out of any common YouTube URL shape.

    A bare id is accepted as-is, so a user can paste either form.
    """
    url = (url or "").strip()
    for pattern in _VIDEO_ID_PATTERNS:
        m = re.search(pattern, url)
        if m:
            return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", url):
        return url
    return None


def fetch_transcript(video_id: str, api_key: str, *, timeout: float = 30.0) -> str:
    """Return the flattened spoken text for one video, or "" if none is available.

    The key travels as a header, never a query param: httpx embeds the request
    URL in its error strings, and those have reached user-visible storage before
    (TMDEV-46).
    """
    resp = httpx.post(
        API_URL,
        headers={"Authorization": f"Basic {api_key}", "Content-Type": "application/json"},
        json={"ids": [video_id]},
        timeout=timeout,
    )
    resp.raise_for_status()
    data = resp.json()

    item = data[0] if isinstance(data, list) and data else {}

    # Response shape: item["tracks"][0]["transcript"] = [{text, start, dur}, ...]
    for track in item.get("tracks", []):
        entries = track.get("transcript", [])
        if entries:
            return " ".join(
                e.get("text", "").replace("\n", " ") for e in entries if e.get("text")
            )

    # Fallback: flat transcript field
    transcript = item.get("transcript")
    if isinstance(transcript, list):
        return " ".join(
            e.get("text", "").replace("\n", " ") for e in transcript if e.get("text")
        )
    if isinstance(transcript, str):
        return transcript.replace("\n", " ")

    return ""
