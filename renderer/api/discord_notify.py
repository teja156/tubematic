"""Discord webhook notifications for the three human checkpoints (TMDEV-5).

Deliberately DB-free and filesystem-free, like postforme.py: the webhook URL
and already-assembled video dicts arrive as arguments, so the settings read
stays with the caller that owns it and every function here is testable without
a network or a database.

Named discord_notify rather than discord so it cannot shadow a `discord`
package for any sibling module in renderer/api/.

**The webhook URL is a credential.** Anyone holding it can post to that channel
as this webhook, which is why it is stored as a `secret`-typed setting and why
nothing here ever lets it into an error string: httpx embeds the request URL in
its exception text, and worker.py persists exception text into the
dashboard-visible comments table. That is exactly how a Gemini key leaked
(TMDEV-46). Every message this module raises or logs goes through redact().

Discord's documented limits, all of which are a 400 when exceeded rather than a
silent truncation — so composition clips on the way in rather than hoping:

    <= 10 embeds per message, <= 25 fields per embed
    title <= 256, description <= 4096, field name <= 256, field value <= 1024
    <= 6000 characters total across every embed in the message

A successful execute-webhook answers 204 with no body (we do not pass ?wait).
"""
import json
import logging
import re
import time

import httpx

# Accepts every host Discord hands out a webhook URL on. The /api/v10 form is
# what the "Copy Webhook URL" button produces on some clients, so an optional
# version segment is part of the shape, not leniency.
_WEBHOOK_RE = re.compile(
    r"^https://(?:ptb\.|canary\.)?discord(?:app)?\.com"
    r"/api(?:/v\d{1,2})?/webhooks/(\d{5,25})/([A-Za-z0-9_-]{20,120})/?$"
)

_TIMEOUT_SECS = 10.0
# The save-time probe is a GET on the webhook URL, which sends no message and
# needs no authentication. Kept short: it runs inside POST /settings, and a
# settings save must not hang on Discord being slow.
_VERIFY_TIMEOUT_SECS = 5.0

# Discord message limits — see the module docstring.
MAX_EMBEDS = 10
MAX_FIELDS_PER_EMBED = 25
MAX_TITLE = 256
MAX_DESCRIPTION = 4096
MAX_FIELD_NAME = 256
MAX_FIELD_VALUE = 1024
MAX_TOTAL_CHARS = 6000

# Topics per bundled message. Well under MAX_FIELDS_PER_EMBED on purpose: 25
# fields at the per-field budgets below would clear 6000 characters and earn a
# 400, and the per-run research caps top out at 6 topics anyway. Anything beyond
# this is counted in the description rather than dropped silently.
TOPICS_PER_MESSAGE = 15
_TOPIC_NAME_BUDGET = 90
_TOPIC_VALUE_BUDGET = 250

# Embed colours, matching the dashboard's own palette so the two read as one
# product: blurple for information, amber for "costs money next", green for done,
# red for "stuck, needs a person".
COLOR_TOPICS = 0x5865F2
COLOR_SCRIPT = 0xF59E0B
COLOR_VIDEO = 0x4ADE80
COLOR_ALERT = 0xEF4444

# Measured across nine finished videos (TMDEV-81): ElevenLabs speaks at a flat
# ~157 wpm, and word count predicts finished duration within ~4%. Only used to
# put a human-readable runtime estimate next to a script that has not been
# voiced yet, so a few seconds of error costs nothing.
SPEAKING_WPM = 157


class DiscordError(Exception):
    """A webhook call that did not succeed. `message` is already redacted."""


# Every other provider here sends its credential as a header, so httpx's own
# "HTTP Request: <method> <url>" INFO line is harmless. A Discord webhook token
# is in the URL by construction, so that line prints a live credential on every
# single request — observed reaching both `docker logs` and a JSONL file.
#
# tubematic_core.logging redacts the JSONL, but two gaps make that insufficient
# on its own: the stdout handler has a plain formatter and no redaction at all,
# and the save-time probe runs *before* the URL is stored, so at that moment
# there is no stored secret for its value axis to match. Fixing it at the source
# closes both.
#
# A filter rather than raising httpx's log level: it rewrites only lines that
# actually contain a webhook URL and leaves every other httpx line — including
# the ones that help debug Gemini and postforme — exactly as they were.
_URL_IN_TEXT_RE = re.compile(
    r"(discord(?:app)?\.com/api(?:/v\d{1,2})?/webhooks/\d+/)([A-Za-z0-9_.-]+)"
)


class _RedactWebhookUrls(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # a malformed record is not ours to fix, but must not
            return True    # be dropped either
        if "webhooks/" in message:
            record.msg = _URL_IN_TEXT_RE.sub(r"\1***", message)
            record.args = ()
        return True


# Installed once, at import. Every process that can reach Discord imports this
# module to do it, so there is no path that sends without the filter in place.
logging.getLogger("httpx").addFilter(_RedactWebhookUrls())


def parse_webhook_url(url: str) -> tuple[str, str]:
    """(webhook_id, token) for a well-formed Discord webhook URL.

    Raises ValueError otherwise. Pure — this is the shape check POST /settings
    applies before it will store anything, and it never touches the network.
    """
    match = _WEBHOOK_RE.match((url or "").strip())
    if not match:
        raise ValueError(
            "discord_webhook_url must look like "
            "https://discord.com/api/webhooks/<id>/<token> — copy it from the "
            "channel's Integrations → Webhooks page"
        )
    return match.group(1), match.group(2)


def redact(text: str, url: str) -> str:
    """Replace the webhook token in `text` with a marker.

    Redacts the token rather than the whole URL so an error still says which
    webhook failed. The id is public in the sense that it is useless alone.
    """
    if not url:
        return text
    try:
        _, token = parse_webhook_url(url)
    except ValueError:
        # Malformed enough that we cannot isolate the token — drop the whole
        # thing rather than leave a half-secret in a persisted message.
        return text.replace(url.strip(), "<discord-webhook-url>")
    return text.replace(token, "***")


# ── Verification ─────────────────────────────────────────────────────────────

def verify_webhook(url: str, *, timeout: float = _VERIFY_TIMEOUT_SECS) -> tuple[str, str]:
    """Probe a webhook URL without sending a message. Returns (verdict, detail).

    verdict is "valid", "invalid" or "unknown". GET on a webhook URL returns the
    webhook object, needs no authentication and posts nothing, so this is free
    to run on every save.

    Tri-state for the same reason onboard/api_keys.py is: only a *positive*
    rejection may gate a save. Discord being unreachable, rate-limiting us or
    answering 5xx all return "unknown", because refusing to store a URL on the
    strength of a timeout would make Settings un-saveable whenever Discord has a
    bad afternoon.
    """
    try:
        parse_webhook_url(url)
    except ValueError as exc:
        return ("invalid", str(exc))

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(url.strip())
    except Exception as exc:
        # Covers httpx.ConnectError/TimeoutException and the two paste failures
        # that do not look like network errors: LocalProtocolError subclasses
        # HTTPError, and UnicodeEncodeError is not an httpx exception at all
        # (TMDEV-52). Never a rejection — see the docstring.
        return ("unknown", redact(f"could not reach Discord: {exc}", url))

    if resp.status_code == 200:
        try:
            body = resp.json()
        except ValueError:
            body = {}
        name = body.get("name") or "webhook"
        channel = body.get("channel_id") or "?"
        return ("valid", f"{name} (channel {channel})")

    # 401 is Invalid Webhook Token, 404 is Unknown Webhook (deleted, or an id
    # that never existed). Both mean this URL will never deliver a message, so
    # both are worth refusing at save time.
    if resp.status_code in (401, 404):
        return ("invalid", redact(_error_detail(resp), url))

    return ("unknown", redact(f"Discord returned HTTP {resp.status_code}", url))


def _error_detail(resp: httpx.Response) -> str:
    try:
        body = resp.json()
        detail = body.get("message") if isinstance(body, dict) else None
        return detail or json.dumps(body)[:200]
    except Exception:
        return (resp.text or f"HTTP {resp.status_code}")[:200]


# ── Sending ──────────────────────────────────────────────────────────────────

def send(url: str, payload: dict, *, timeout: float = _TIMEOUT_SECS) -> None:
    """POST one message. Raises DiscordError on any non-2xx.

    A 429 is retried once after the retry_after Discord names, then given up
    on — the caller's marker stays unadvanced, so the next sweep tries again
    anyway and there is no value in blocking this pass any longer.
    """
    parse_webhook_url(url)  # never send to something that is not a webhook
    target = url.strip()

    for attempt in (1, 2):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(target, json=payload)
        except Exception as exc:
            raise DiscordError(redact(f"Discord request failed: {exc}", url)) from None

        if resp.status_code < 300:
            return

        if resp.status_code == 429 and attempt == 1:
            time.sleep(_retry_after(resp))
            continue

        raise DiscordError(
            redact(f"Discord returned HTTP {resp.status_code}: {_error_detail(resp)}", url)
        )


def _retry_after(resp: httpx.Response) -> float:
    """Seconds Discord asked us to wait, clamped so a bad value cannot stall
    the worker loop — this runs inline in the render worker's tick."""
    try:
        value = float(resp.json().get("retry_after", 1.0))
    except Exception:
        value = 1.0
    return max(0.0, min(value, 5.0))


# ── Composition ──────────────────────────────────────────────────────────────
#
# Every builder takes plain dicts (a videos row plus whatever the caller could
# cheaply add, e.g. project_name) and returns a ready payload. No DB, no files,
# no clock — so the limit handling below is exhaustively testable.

def _clip(text, limit: int) -> str:
    text = "" if text is None else str(text).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _display_name(video: dict) -> str:
    """The short title, falling back to the full topic.

    `or`, never a nullish-style check: title is NOT NULL DEFAULT '' and every
    row predating TMDEV-82 holds the empty string rather than NULL.
    """
    return video.get("title") or video.get("topic") or video.get("id") or "untitled"


def _link(base_url: str, path: str) -> str:
    """A dashboard URL, or "" when no base URL is configured."""
    base = (base_url or "").strip().rstrip("/")
    return f"{base}{path}" if base else ""


def _total_chars(embeds: list) -> int:
    """What Discord counts against the 6000 limit: every visible string in
    every embed."""
    total = 0
    for embed in embeds:
        total += len(embed.get("title", "")) + len(embed.get("description", ""))
        total += len((embed.get("footer") or {}).get("text", ""))
        total += len((embed.get("author") or {}).get("name", ""))
        for field in embed.get("fields", []):
            total += len(field.get("name", "")) + len(field.get("value", ""))
    return total


def _enforce_limits(embeds: list) -> list:
    """Last-ditch trim so a payload can never earn a 400.

    The per-item budgets above already keep every message well inside the
    limits; this exists because the cost of being wrong is asymmetric — a
    rejected message is a notification the human never gets, and nothing
    downstream would tell them it happened.
    """
    embeds = embeds[:MAX_EMBEDS]
    for embed in embeds:
        if "title" in embed:
            embed["title"] = _clip(embed["title"], MAX_TITLE)
        if "description" in embed:
            embed["description"] = _clip(embed["description"], MAX_DESCRIPTION)
        if "fields" in embed:
            embed["fields"] = [
                {
                    "name": _clip(f.get("name"), MAX_FIELD_NAME) or "—",
                    "value": _clip(f.get("value"), MAX_FIELD_VALUE) or "—",
                    **({"inline": True} if f.get("inline") else {}),
                }
                for f in embed["fields"][:MAX_FIELDS_PER_EMBED]
            ]

    # Bounded rather than `while`: this runs inside the render worker's tick,
    # and every iteration either removes a field or halves a description, so
    # the bound is only ever reached by a shape this module cannot produce.
    # Spinning there would stall rendering, which is far worse than a 400.
    for _ in range(MAX_EMBEDS * MAX_FIELDS_PER_EMBED + MAX_EMBEDS):
        if _total_chars(embeds) <= MAX_TOTAL_CHARS:
            break
        # Drop trailing fields first; they are the repeated, least essential
        # part of every message here.
        for embed in reversed(embeds):
            if embed.get("fields"):
                embed["fields"].pop()
                break
        else:
            # No fields left anywhere — halve the longest description instead.
            longest = max(embeds, key=lambda e: len(e.get("description", "")))
            if not longest.get("description"):
                break
            longest["description"] = _clip(
                longest["description"], len(longest["description"]) // 2
            )
    return embeds


def build_topics_payload(videos: list, *, base_url: str = "") -> dict:
    """One bundled message for N newly proposed topics.

    Bundled rather than one message per topic because a research run files them
    in bulk — six separate pings for one run is what makes a notification
    channel get muted.
    """
    shown = videos[:TOPICS_PER_MESSAGE]
    overflow = len(videos) - len(shown)

    lines = []
    link = _link(base_url, "/topics")
    if link:
        lines.append(f"[Review them in the dashboard]({link})")
    if overflow:
        lines.append(f"…and **{overflow} more** not listed here.")

    fields = []
    for video in shown:
        # 0 is "unscored": a video submitted from the dashboard's New Video page
        # has no agent to score it, and nothing else files below 5.
        score = video.get("producibility_score") or 0
        facts = [
            str(video.get("strategy") or "manual"),
            f"score {score}/10" if score > 0 else "unscored",
        ]
        if video.get("project_name"):
            facts.append(str(video["project_name"]))
        brief = _clip(video.get("topic"), _TOPIC_VALUE_BUDGET - len(" · ".join(facts)) - 4)
        fields.append({
            "name": _clip(_display_name(video), _TOPIC_NAME_BUDGET),
            "value": f"`{' · '.join(facts)}`\n{brief}",
        })

    count = len(videos)
    embed = {
        "title": f"🧠 {count} new topic{'s' if count != 1 else ''} proposed",
        "color": COLOR_TOPICS,
        "fields": fields,
        "footer": {"text": "Tubematic · approve or reject on the Topics page"},
    }
    if lines:
        embed["description"] = "\n".join(lines)
    return {"embeds": _enforce_limits([embed])}


def build_script_ready_payload(video: dict, *, base_url: str = "") -> dict:
    """One video has a script waiting for a human.

    Says outright that approving spends money — this is the checkpoint where
    ElevenLabs charges per character and the charge is not refundable.
    """
    script = (video.get("script") or "").strip()
    words = len(script.split())
    parts = []
    link = _link(base_url, "/")
    if link:
        parts.append(f"[Open the pipeline]({link})")
    if script:
        parts.append(f"> {_clip(script, 600)}")
    parts.append("Approving voices the script — ElevenLabs charges per character.")

    fields = [{"name": "Length", "value": f"{words} words · ~{_runtime(words)}", "inline": True}]
    if video.get("strategy"):
        fields.append({"name": "Strategy", "value": str(video["strategy"]), "inline": True})
    if video.get("project_name"):
        fields.append({"name": "Project", "value": str(video["project_name"]), "inline": True})
    if video.get("voice_name"):
        fields.append({"name": "Voice", "value": str(video["voice_name"]), "inline": True})
    if video.get("script_profile_name"):
        fields.append({"name": "Script profile", "value": str(video["script_profile_name"]), "inline": True})

    return {"embeds": _enforce_limits([{
        "title": f"📝 Script ready — {_clip(_display_name(video), 200)}",
        "description": "\n\n".join(parts),
        "color": COLOR_SCRIPT,
        "fields": fields,
        "footer": {"text": f"Tubematic · {video.get('id', '')}"},
    }])}


def build_video_ready_payload(video: dict, *, base_url: str = "") -> dict:
    """One video has rendered and is waiting for sign-off."""
    parts = []
    link = _link(base_url, "/library")
    if link:
        parts.append(f"[Watch it in the library]({link})")
    parts.append("Nothing is published until you approve it.")

    fields = []
    if video.get("duration_secs"):
        fields.append({"name": "Duration", "value": _duration(video["duration_secs"]), "inline": True})
    fields.append({"name": "Version", "value": f"v{video.get('video_version', 1)}", "inline": True})
    if video.get("review_summary"):
        fields.append({"name": "AI review", "value": _clip(video["review_summary"], MAX_FIELD_VALUE)})

    return {"embeds": _enforce_limits([{
        "title": f"🎬 Video ready — {_clip(_display_name(video), 200)}",
        "description": "\n\n".join(parts),
        "color": COLOR_VIDEO,
        "fields": fields,
        "footer": {"text": f"Tubematic · {video.get('id', '')}"},
    }])}


def build_voicing_stalled_payload(video: dict, *, base_url: str = "") -> dict:
    """One video has sat in VOICING without being voiced (TMDEV-112).

    Not a checkpoint announcement — nothing is waiting on the human by design.
    Every poll tick picks a VOICING video up, so one still there after several
    means something keeps failing: an agent declining generate_voice, a voicing
    error, or the poller not running. From outside those all look like an agent
    that simply has not run yet, which is why this exists at all.
    """
    parts = []
    link = _link(base_url, "/")
    if link:
        parts.append(f"[Open the pipeline]({link})")
    parts.append(
        f"Approved for voicing **{elapsed(video.get('stalled_secs'))} ago** and still "
        "not voiced. Every poll tick picks it up, so something keeps failing — the "
        "video's comments and the poll log say what.")
    return {"embeds": _enforce_limits([{
        "title": f"⚠️ Stuck in voicing — {_clip(_display_name(video), 200)}",
        "description": "\n\n".join(parts),
        "color": COLOR_ALERT,
        "footer": {"text": f"Tubematic · {video.get('id', '')}"},
    }])}


def elapsed(secs) -> str:
    """A coarse age for a human — "1h 31m", "2d 4h" — where _duration's
    seconds would be noise."""
    mins = max(0, int(secs or 0)) // 60
    days, mins = divmod(mins, 24 * 60)
    hours, mins = divmod(mins, 60)
    if days:
        return f"{days}d {hours}h"
    return f"{hours}h {mins:02d}m" if hours else f"{mins}m"


def _runtime(words: int) -> str:
    return _duration(round(words / SPEAKING_WPM * 60)) if words else "unknown"


def _duration(secs) -> str:
    secs = int(secs or 0)
    return f"{secs // 60}m {secs % 60:02d}s" if secs >= 60 else f"{secs}s"
