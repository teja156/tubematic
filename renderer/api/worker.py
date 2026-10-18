#!/usr/bin/env python3
"""Tubematic render worker (TMDEV-32).

Standalone process (own container: tubematic-renderer) that polls the shared
SQLite DB for videos in RENDER_QUEUED status, atomically claims one, renders
it via Remotion, and runs the same AI-review/failure tail that used to live
in the Flask process's in-memory queue + daemon thread (renderer/api/server.py,
prior to this ticket). Making videos.status the durable queue means a worker
restart can't lose a queued or in-flight job — see _reconcile_rendering_videos.

Run: python3 worker.py
"""
import calendar
import datetime as dt
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
import zoneinfo
from pathlib import Path

import ai_review
import autopilot
import db
import discord_notify
import hosttz
import metrics
import pipeline
import postforme
from tubematic_core import jobfiles as tjobs
from tubematic_core import logging as tlog
from tubematic_core import prices as tprices
from tubematic_core import usage as tusage

DB_PATH = os.getenv("TUBEMATIC_DB", "/data/tubematic.db")
OUTPUT_DIR = Path(os.getenv("OUTPUT_BASE_PATH", "/output_videos"))
REMOTION_DIR = Path("/app/remotion")
LOG_DIR = Path(os.getenv("TUBEMATIC_LOG_DIR", "/logs"))
CHROMIUM_BIN = os.getenv("CHROMIUM_BIN", "/usr/bin/chromium")

POLL_INTERVAL_SECS = int(os.getenv("RENDER_POLL_INTERVAL_SECS", "20"))
# render_timeout_secs is a live pipeline setting (TMDEV-57), not a fixed
# constant — read via _render_timeout_secs() at the point of use so it can be
# changed via onboard/dashboard without a worker restart.

# gemini_feedback is stored WHOLE — no cap. The review prompt no longer limits
# the number of must-fix entries or their length, so any cap here would silently
# drop real blocking defects, and this column is what the agent actually acts on
# (get_video returns it in full). One row per video, overwritten each round, so
# unbounded length costs nothing that matters.
#
# The comment thread keeps its cap: it is append-only, and it is a pointer to the
# review rather than the review itself. _format_feedback orders
# Overall -> Must fix -> Suggestions, so a truncated comment loses suggestions
# first and always keeps the blocking items, and _truncate_comment appends an
# explicit marker naming gemini_feedback as the full copy.
_COMMENT_MAX_CHARS = 2000
_COMMENT_TRUNCATION_NOTE = (
    "\n\n… truncated — read `gemini_feedback` on this video for the complete review."
)


def _truncate_comment(text: str) -> str:
    """Cap a comment, saying so when it bites.

    Silent truncation is the failure mode worth avoiding: the agent cannot tell
    a short review from a clipped one, and since must-fix entries are now
    unbounded a clipped comment can hide blocking defects entirely.
    """
    text = text or ""
    if len(text) <= _COMMENT_MAX_CHARS:
        return text
    keep = _COMMENT_MAX_CHARS - len(_COMMENT_TRUNCATION_NOTE)
    return text[:keep].rstrip() + _COMMENT_TRUNCATION_NOTE


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [worker] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    stream=sys.stdout,
)
log = logging.getLogger("worker")


def _setting(key: str, default: str) -> str:
    """Read a runtime setting from the settings table; fall back to env then default.

    The settings table is the live source of truth; env is a fallback only,
    never written by onboarding.

    A **blank** row falls through rather than winning, which matters since
    TMDEV-73: onboarding seeds "" for every credential it did not ask about, so
    an existing-but-empty row would otherwise shadow a key supplied through the
    container environment — silently skipping AI review on a stack that has one.
    Matches mcp/server.py's key helpers and pipeline.py's _secret, which both
    use `stored or env`. No caller wants a blank: the ints would raise on
    int(""), and the model/bool keys have no meaningful empty value.
    """
    try:
        with db.conn(DB_PATH) as con:
            row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is not None and row["value"] != "":
            return row["value"]
    except Exception:
        pass
    return os.getenv(key.upper(), default)


def _max_render_retries() -> int:
    try:
        return int(_setting("max_render_retries", "1"))
    except (ValueError, TypeError):
        return 1


def _max_ai_review_loops() -> int:
    """How many AI reviews a video gets before one is force-accepted.

    Split out from the render-retry cap by VQA-7. The two budgets used to be one
    knob, so lowering the review loop — which VQA-7 wanted, since a review
    round can now cost a paid re-voice and its findings were often cosmetic —
    would have halved the render crash/timeout retry budget as a side effect.
    Those failures are unrelated, and TMDEV-57 showed a large video
    legitimately needing a second render attempt after a timeout.
    """
    try:
        return int(_setting("ai_review_max_loops", "1"))
    except (ValueError, TypeError):
        return 1


def _render_timeout_secs() -> int:
    try:
        return int(_setting("render_timeout_secs", "2400"))
    except (ValueError, TypeError):
        return 2400


# ── Publishing (TMDEV-83) ───────────────────────────────────────────────────
#
# PUBLISHING is unlike every other status this worker touches: Flask sets it,
# and the worker only observes it. RENDER_QUEUED and RENDERING are both set by
# the worker itself, so their backstops can key off a retry counter the worker
# increments. A publish has no crash to count — only an absence — so the
# backstop here is a wall clock instead. Do not "fix" it into a counter.
#
# The clock is measured from video_publications.created_at, deliberately NOT
# videos.updated_at: that column is the FIFO ordering key for the atomic render
# claim, and this poll writes to it.
_PUBLISH_TIMEOUT_SECS = 3600

# Metrics move slowly and every published video is polled on every pass, so an
# unthrottled loop would hit postforme once per worker iteration for the life of
# the install.
#
# The last-poll timestamp is a settings row rather than a module global, for the
# same reason last_research_at is: a global resets on every worker restart, so a
# container that restarts often would sweep every published video each time.
_METRICS_INTERVAL_SECS = 3600
_METRICS_STAMP_KEY = "last_metrics_poll_at"

# Model prices (TMDEV-107) are synced weekly on the same settings-row throttle,
# for the same restart reason. Weekly, not daily: the upstream file changes
# many times a day, but a three-month diff showed one structural change to the
# models we use.
_PRICE_SYNC_INTERVAL_SECS = 7 * 24 * 3600
_PRICE_SYNC_STAMP_KEY = "last_price_sync_at"


def _publishing_key() -> str:
    """The postforme key, or "" when publishing is off or unconfigured."""
    if _setting("publishing_enabled", "false").lower() != "true":
        return ""
    return _setting("postforme_api_key", "")


def _publication_error(result: dict) -> str:
    """A persistable failure reason from one post result.

    Goes through postforme.scrub first: the result payload is one of the places
    that can carry the channel's OAuth credentials, and this string lands in
    video_publications.error, which the dashboard renders.
    """
    error = postforme.scrub(result.get("error"))
    if isinstance(error, dict):
        return str(error.get("message") or json.dumps(error))[:500]
    return str(error or "publish failed")[:500]


def _poll_publishing_videos() -> None:
    """Advance PUBLISHING videos toward PUBLISHED or FAILED.

    One non-blocking pass, called before the render claim so publishing can
    never starve rendering.

    Completion is decided by counting result rows against targets, never by
    reading a status: postforme's result payload has no pending state, so a
    target that has not published yet simply has no row.
    """
    api_key = _publishing_key()
    if not api_key:
        return

    _release_due_schedules()

    with db.conn(DB_PATH) as con:
        video_ids = [r["id"] for r in con.execute(
            "SELECT id FROM videos WHERE status = 'PUBLISHING'")]

    for video_id in video_ids:
        try:
            _settle_publication(video_id, api_key)
        except postforme.PostformeError as e:
            # An outage is not a publish failure. Marking the video FAILED
            # because the status API blinked would strand a video that is
            # already live on every platform — leave it for the next tick.
            log.warning(f"[{video_id}] publish poll deferred: {e}", extra={"video_id": video_id})
        except Exception as e:
            log.exception(f"[{video_id}] publish poll error: {e}")


def _release_due_schedules() -> None:
    """SCHEDULED -> PUBLISHING once scheduled_at has passed (TMDEV-133).

    postforme sends the post itself; this only starts watching for its results.
    The rows' created_at is reset in the same transaction because the publish
    deadline is measured from it: measured from when the post was scheduled,
    a post scheduled more than an hour ahead would have every target failed on
    its first pass, before postforme had even picked it up.

    Both sides of the comparison are db._now()-shaped UTC strings, so a string
    comparison orders them correctly.
    """
    now = db._now()
    with db.conn(DB_PATH) as con:
        due = [r["id"] for r in con.execute(
            "SELECT id FROM videos WHERE status = 'SCHEDULED' AND scheduled_at <= ?", (now,))]
        for video_id in due:
            moved = con.execute(
                "UPDATE videos SET status = 'PUBLISHING', updated_at = ?"
                " WHERE id = ? AND status = 'SCHEDULED'", (now, video_id)).rowcount
            if moved:
                con.execute(
                    "UPDATE video_publications SET created_at = ?, updated_at = ?"
                    " WHERE video_id = ? AND status = 'PENDING'", (now, now, video_id))
                log.info(f"[{video_id}] scheduled post is due — watching for results",
                         extra={"video_id": video_id})


def _schedule_pending(video_id: str) -> bool:
    with db.conn(DB_PATH) as con:
        row = con.execute("SELECT scheduled_at FROM videos WHERE id = ?", (video_id,)).fetchone()
    return bool(row and row["scheduled_at"] and row["scheduled_at"] > db._now())


def _settle_publication(video_id: str, api_key: str) -> None:
    with db.conn(DB_PATH) as con:
        pubs = [dict(r) for r in con.execute(
            "SELECT * FROM video_publications WHERE video_id = ? AND status = 'PENDING'",
            (video_id,))]
        done = con.execute(
            "SELECT COUNT(*) AS c FROM video_publications"
            " WHERE video_id = ? AND status != 'PENDING'", (video_id,)).fetchone()["c"]

    if not pubs and not done:
        # No rows at all. Flask writes them at the claim (TMDEV-97), so this is
        # only reachable for a publish that was already mid-flight when the
        # stack was upgraded from a version that wrote them after create_post.
        # A real post may exist, so ask postforme before writing this off —
        # marking it FAILED without checking leaves a live social post that
        # nothing local knows about.
        if _recover_orphan_publication(video_id, api_key):
            return
        log.error(f"[{video_id}] PUBLISHING with no publication rows and no post "
                  f"at postforme — failing it", extra={"video_id": video_id})
        db.set_status(DB_PATH, video_id, "FAILED", only_if="PUBLISHING")
        _comment(video_id, "Publishing failed: no post was created and no publication "
                           "records were written. Nothing was posted; it can be published "
                           "again.")
        return

    in_progress = [p for p in pubs if not p["postforme_post_id"]]
    if in_progress:
        _settle_in_progress(video_id, api_key, in_progress)
        return

    # A post that is not due yet — reached when a scheduled publish's
    # create_post was ambiguous and the post was adopted by external_id. It has
    # no results until postforme sends it, so settling it now would fail every
    # target at the deadline. It waits in SCHEDULED like any other.
    if pubs and _schedule_pending(video_id):
        db.set_status(DB_PATH, video_id, "SCHEDULED", only_if="PUBLISHING")
        return

    post_id = pubs[0]["postforme_post_id"] if pubs else ""
    results = {r.get("social_account_id"): r
               for r in (postforme.get_post_results(api_key, post_id=post_id) if post_id else [])}

    now = db._now()
    expired = _publish_deadline_passed(pubs)
    for pub in pubs:
        result = results.get(pub["social_account_id"])
        if result is None:
            if not expired:
                continue
            _write_result(pub["id"], "FAILED", "",
                          "postforme did not report a result before the publish timeout.", now)
            continue
        if result.get("success"):
            url = (postforme.scrub(result.get("platform_data")) or {}).get("url", "")
            _write_result(pub["id"], "PUBLISHED", url, "", now)
        else:
            _write_result(pub["id"], "FAILED", "", _publication_error(result), now)

    _derive_video_status(video_id)


def _settle_in_progress(video_id: str, api_key: str, in_progress: list) -> None:
    """Rows with no post id yet: Flask claimed the video and is still publishing.

    Flask writes the rows at the claim and fills in the post id only once
    create_post returns, so an empty post id is a publish in flight — the
    upload alone can outlast many ticks. Inferring a crash from it is exactly
    the race that failed live videos mid-upload (TMDEV-97).

    So a live post found by external_id is adopted straight away — that is
    what recovers an ambiguous create_post on the next tick — but the absence
    of one is only acted on once the rows are older than the publish deadline.
    Do not "fix" the wait with a shorter grace period: the upload has no hard
    upper bound, so any fixed number is a guess, and a slow fail is safe where
    a fast one abandons a live post. A dead post (every target failed) is not
    adopted early, because it may be an earlier attempt's post under the same
    external_id rather than this one's.
    """
    post = postforme.find_post_by_external_id(api_key, external_id=video_id)
    expired = _publish_deadline_passed(in_progress)
    if post and (post.get("live") or expired):
        _adopt_post(video_id, post)
        return
    if not expired:
        return

    # One transaction, and every write re-checks that the publish is still in
    # flight: Flask filling a post id in between two separate writes would
    # leave a FAILED video with pending rows that nothing ever polls again.
    now = db._now()
    with db.conn(DB_PATH) as con:
        con.execute(
            "UPDATE video_publications SET status = 'FAILED', error = ?, updated_at = ?"
            " WHERE video_id = ? AND status = 'PENDING' AND postforme_post_id = ''",
            ("No post was created at postforme before the publish deadline.", now, video_id))
        failed = con.execute(
            "UPDATE videos SET status = 'FAILED', updated_at = ?"
            " WHERE id = ? AND status = 'PUBLISHING' AND NOT EXISTS ("
            "  SELECT 1 FROM video_publications"
            "  WHERE video_id = ? AND status = 'PENDING' AND postforme_post_id != '')",
            (now, video_id, video_id)).rowcount
    if not failed:
        return
    log.error(f"[{video_id}] publish never created a post before the deadline — failing it",
              extra={"video_id": video_id})
    _comment(video_id, "Publishing failed: no post was created at postforme before the "
                       "publish deadline. Use Retry publishing — it checks postforme first, "
                       "so it will not post twice.")


def _adopt_post(video_id: str, post: dict) -> int:
    """Attach a postforme post to this video's publication rows.

    Fills the post id into the in-progress rows, and inserts a row for any
    target the post has that no row covers. Guarded on the post id being
    empty, so Flask filling it in concurrently is harmless — both write the
    same post. Returns how many targets the post has.

    created_at is reset with it, because the publish deadline is measured from
    that column: without the reset a post adopted near the deadline would have
    its unreported targets failed on the very next pass.
    """
    targets = postforme.publication_targets(post)
    now = db._now()
    with db.conn(DB_PATH) as con:
        con.execute(
            "UPDATE video_publications SET postforme_post_id = ?, created_at = ?, updated_at = ?"
            " WHERE video_id = ? AND postforme_post_id = ''", (post["id"], now, now, video_id))
        known = {r["social_account_id"] for r in con.execute(
            "SELECT social_account_id FROM video_publications WHERE video_id = ?",
            (video_id,))}
        for account_id, platform in targets:
            if account_id in known:
                continue
            con.execute(
                "INSERT INTO video_publications (id, video_id, platform,"
                " social_account_id, postforme_post_id, status, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)",
                (str(uuid.uuid4()), video_id, platform, account_id, post["id"], now, now))
    log.warning(f"[{video_id}] adopted postforme post {post['id']} "
                f"({len(targets)} target(s))", extra={"video_id": video_id})
    return len(targets)


def _recover_orphan_publication(video_id: str, api_key: str) -> bool:
    """Adopt a post that exists at postforme but has no local rows.

    Found by `external_id`, which every publish stamps with the video_id for
    precisely this. Returns True when rows were written and the video should
    keep polling; False when postforme genuinely has no such post.

    Rebuilt from the post's own `social_accounts`, not from the original
    request, because the request is gone — this runs in a different process from
    the one that made it, possibly after a restart.
    """
    post = postforme.find_post_by_external_id(api_key, external_id=video_id)
    if not post or not post.get("id") or not postforme.publication_targets(post):
        return False

    count = _adopt_post(video_id, post)
    _comment(video_id, f"Recovered a post that was created at postforme but not recorded "
                       f"locally ({count} target(s)). Publishing continues from here — "
                       f"the video was not published twice.")
    return True


def _publish_deadline_passed(pubs: list) -> bool:
    """Whether the oldest still-pending target has run out of time."""
    if not pubs:
        return False
    oldest = min(p["created_at"] for p in pubs)
    try:
        # timegm, not mktime: created_at is UTC (db._now uses gmtime), and
        # mktime would read it as local time — an offset that also moves with
        # DST, so the backstop would fire early or late by hours.
        created = calendar.timegm(time.strptime(oldest, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return False
    return time.time() - created > _PUBLISH_TIMEOUT_SECS


def _write_result(publication_id: str, status: str, url: str, error: str, now: str) -> None:
    with db.conn(DB_PATH) as con:
        con.execute(
            "UPDATE video_publications SET status = ?, post_url = ?, error = ?,"
            " published_at = ?, updated_at = ? WHERE id = ?",
            (status, url, error, now if status == "PUBLISHED" else "", now, publication_id))


def _derive_video_status(video_id: str) -> None:
    """videos.status from its publication rows, once none are still pending.

    PUBLISHED if ANY target succeeded. There is no un-publish, so a video live
    on two of four accounts genuinely is published; calling it FAILED would lie
    about the accounts that did post, and the per-account failures are visible
    on their own rows. FAILED only when every target failed.
    """
    with db.conn(DB_PATH) as con:
        rows = con.execute(
            "SELECT status, COUNT(*) AS c FROM video_publications"
            " WHERE video_id = ? GROUP BY status", (video_id,)).fetchall()
    counts = {r["status"]: r["c"] for r in rows}
    if counts.get("PENDING"):
        return

    published = counts.get("PUBLISHED", 0)
    failed = counts.get("FAILED", 0)
    if published:
        db.set_status(DB_PATH, video_id, "PUBLISHED", only_if="PUBLISHING")
        if failed:
            _comment(video_id,
                     f"Published to {published} account(s); {failed} failed. "
                     "See the publication list for the per-account errors.")
    else:
        db.set_status(DB_PATH, video_id, "FAILED", only_if="PUBLISHING")
        _comment(video_id, f"Publishing failed on all {failed} target(s).")


def _comment(video_id: str, text: str) -> None:
    try:
        db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(text))
    except Exception:
        log.exception(f"[{video_id}] could not write comment")


def _metrics_due() -> bool:
    stamp = _setting(_METRICS_STAMP_KEY, "")
    if not stamp:
        return True
    try:
        last = calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return True
    return time.time() - last >= _METRICS_INTERVAL_SECS


def _price_sync_due() -> bool:
    stamp = _setting(_PRICE_SYNC_STAMP_KEY, "")
    if not stamp:
        return True
    try:
        last = calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return True
    return time.time() - last >= _PRICE_SYNC_INTERVAL_SECS


def _sync_prices_if_due() -> None:
    """Weekly model-price sync, delegating to tubematic_core.prices.sync_prices.

    Shared with Settings → Sync now. A failure keeps every existing price and
    is recorded for Settings to show; it never stops this loop, and a render
    never waits on the network for a price — calls are priced from the table.
    """
    if not _price_sync_due():
        return
    try:
        with db.conn(DB_PATH) as con:
            # Stamped before the work, like the metrics pass: a sync that dies
            # must not retry on the next iteration 20 seconds later.
            con.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_PRICE_SYNC_STAMP_KEY, db._now()))
        with db.conn(DB_PATH) as con:
            result = tprices.sync_prices(con)
        if result["updated"] or result["rejected"] or result["error"]:
            log.info(f"price sync: {len(result['updated'])} updated, "
                     f"{len(result['rejected'])} rejected"
                     + (f", failed: {result['error']}" if result["error"] else ""))
    except Exception:
        log.exception("price sync pass failed")


def _force_metrics_due(db_path: str) -> None:
    """Test seam: clear the rate-limit stamp so the next pass fetches again."""
    with db.conn(db_path) as con:
        con.execute("DELETE FROM settings WHERE key = ?", (_METRICS_STAMP_KEY,))


# ── Auto Pilot (TMDEV-139) ────────────────────────────────────────────────────
# For the projects selected on the dashboard, this pass does what a human does
# at each checkpoint: approves the topic, the script and the finished video,
# then schedules the post. It runs here, server-side, and not in the agent:
# the agent's rule that it never moves a video out of a checkpoint stays whole,
# and no MCP tool gains the power to approve or publish.
#
# It shares the worker's one loop, so an approval can wait behind a render for
# as long as that render takes.

_AUTO_PILOT_APPROVALS = {
    "TOPIC_PROPOSED": ("TOPIC_APPROVED", "topic"),
    "SCRIPT_READY":   ("VOICING", "script"),
    "VIDEO_READY":    ("VIDEO_APPROVED", "video"),
}

# Seconds to wait after the 1st, 2nd and every later failed publish attempt on
# one video. A failed upload returns the video to VIDEO_APPROVED, where the
# next tick would otherwise retry it, and comment on it, every 20 seconds.
# In memory: a restart retrying once more is harmless.
_AUTO_PILOT_BACKOFF_SECS = (15 * 60, 60 * 60, 6 * 60 * 60)
_auto_pilot_retry: dict = {}


def _sweep_auto_pilot() -> None:
    """One Auto Pilot pass. Never raises — see _sweep_retention."""
    try:
        _auto_pilot_once()
    except Exception:  # noqa: BLE001 - see _sweep_retention's docstring
        log.exception("Auto Pilot sweep failed")


def _auto_pilot_once() -> None:
    with db.conn(DB_PATH) as con:
        settings = pipeline._read_all_settings(con)
        config = pipeline._auto_pilot_config(con)
        in_flight = pipeline.in_flight_count(con, config["projects"])
    # A paused pipeline pauses Auto Pilot too: pause is the one switch an
    # operator reaches for to stop spend, and approving a script spends.
    if not settings["auto_pilot_enabled"] or settings["pipeline_paused"]:
        return
    if not config["projects"]:
        return
    # The in-progress limit (TMDEV-150) gates only the paid gate, SCRIPT_READY
    # -> VOICING, and topic approvals once it is full. Both passes always run:
    # approving a finished video and scheduling it move a video within the
    # count, never into it, and scheduling is the only thing that drains it.
    # Stopping them at the limit stranded approved videos with nothing moving.
    # A video enters the count only through the gate, and the gate is budgeted
    # against the count, so a pass cannot overshoot. None means no limit.
    ceiling = settings["auto_pilot_max_in_flight"]
    room = max(0, ceiling - in_flight) if ceiling else None
    _auto_pilot_approve(settings, config, room)
    _auto_pilot_publish(settings, config)


def _auto_pilot_block_reason(con, video: dict, settings: dict) -> str:
    """Why a dashboard approval of this video would be refused, or "".

    Auto Pilot must not be a way around the two checks the approving PATCH
    makes: approving here what the dashboard refuses would send the video on
    to fail later, after money was spent.
    """
    if video["status"] == "TOPIC_PROPOSED":
        if pipeline._illustrated_needs_key(con, video["visual_style"] or ""):
            return ("its visual style is illustrated, which needs an OpenAI API key and "
                    "none is stored. Add the key in Settings, or change the style and "
                    "approve the topic yourself.")
    if video["status"] == "SCRIPT_READY":
        try:
            video["script_segments"] = json.loads(video["script_segments"] or "null")
        except ValueError:
            video["script_segments"] = None
        voice_id, conflicts = pipeline._voice_state(video, settings)
        if voice_id in conflicts:
            return (f"its script cannot be spoken by its voice: {conflicts[voice_id]} "
                    "Pick another voice and approve the script yourself, or request "
                    "a revision.")
    return ""


def _auto_pilot_approve(settings: dict, config: dict, room=None) -> None:
    """Approve each checkpoint for the selected projects.

    `room` is how many more videos may pass the paid gate this pass (None: no
    limit). A video that has already been voiced holds its slot in the count,
    so re-approving it after a revision uses no room; budgeting it again would
    let a full set of revisions waiting at SCRIPT_READY hold the gate shut for
    good. A new script uses one; a new topic waits while there is none left.
    VIDEO_READY is never held back.
    """
    projects = list(config["projects"])
    statuses = list(_AUTO_PILOT_APPROVALS)
    with db.conn(DB_PATH) as con:
        rows = [dict(r) for r in con.execute(
            "SELECT id, status, updated_at, voice_id, visual_style, script, script_segments,"
            " voice_file_path, auto_pilot_blocked FROM videos"
            " WHERE archived_at IS NULL AND status IN (%s) AND project_id IN (%s)"
            " ORDER BY updated_at ASC"
            % (",".join("?" * len(statuses)), ",".join("?" * len(projects))),
            statuses + projects)]
    for video in rows:
        video_id, status = video["id"], video["status"]
        new_status, what = _AUTO_PILOT_APPROVALS[status]
        budgeted = (room is not None and status != "VIDEO_READY"
                    and not video["voice_file_path"])
        if budgeted and room <= 0:
            continue
        now = db._now()
        with db.conn(DB_PATH) as con:
            reason = _auto_pilot_block_reason(con, video, settings)
            if reason:
                # Re-checked every tick, commented once per arrival: the mark
                # is this arrival's status and time. Written without touching
                # updated_at, which is the mark's own key.
                mark = f"{status}@{video['updated_at']}"
                if video["auto_pilot_blocked"] != mark:
                    told = con.execute(
                        "UPDATE videos SET auto_pilot_blocked = ?"
                        " WHERE id = ? AND status = ? AND updated_at = ?",
                        (mark, video_id, status, video["updated_at"])).rowcount
                    if told:
                        con.execute(
                            "INSERT INTO comments (video_id, author, content, created_at)"
                            " VALUES (?, 'agent', ?, ?)",
                            (video_id, _truncate_comment(
                                f"Auto Pilot did not approve this {what}: {reason}"), now))
                continue
            # The same writes a dashboard approval makes (patch_video), under
            # the same guard: a human who acted first wins, and an archived
            # video is never moved.
            approved = con.execute(
                "UPDATE videos SET status = ?, updated_at = ?, agent_no_progress_count = 0,"
                " agent_stuck_at = NULL WHERE id = ? AND status = ? AND archived_at IS NULL",
                (new_status, now, video_id, status)).rowcount
            if approved:
                con.execute(
                    "INSERT INTO comments (video_id, author, content, created_at)"
                    " VALUES (?, 'agent', ?, ?)",
                    (video_id, f"Approved automatically by Auto Pilot: {what}. "
                               f"No human reviewed it.", now))
        if approved:
            if budgeted and status == "SCRIPT_READY":
                room -= 1
            log.info(f"[{video_id}] Auto Pilot approved {status} -> {new_status}",
                     extra={"video_id": video_id})


def _auto_pilot_zone() -> tuple:
    """(name, tzinfo) days are cut in: the host's zone, else UTC."""
    name = hosttz.host_timezone()["timezone"]
    if name:
        try:
            return name, zoneinfo.ZoneInfo(name)
        except Exception:  # noqa: BLE001 - an unloadable zone must not stop posting
            pass
    return "UTC", dt.timezone.utc


def _parse_utc(stamp: str):
    try:
        return dt.datetime.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def _account_post_times(account_ids: list) -> dict:
    """{account_id: [when each of its posts went or will go out]}.

    Every non-failed publication counts, whoever started it, so a manual
    publish or schedule uses up the account's gap and daily number too. A
    published row is timed by when it was seen published, a waiting one by its
    video's schedule, and a publish in flight by its row.
    """
    times: dict = {a: [] for a in account_ids}
    with db.conn(DB_PATH) as con:
        rows = con.execute(
            "SELECT vp.social_account_id AS account, vp.status, vp.published_at,"
            " vp.created_at, v.scheduled_at FROM video_publications vp"
            " JOIN videos v ON v.id = vp.video_id"
            " WHERE vp.status != 'FAILED' AND vp.social_account_id IN (%s)"
            % ",".join("?" * len(account_ids)), account_ids).fetchall()
    for row in rows:
        if row["status"] == "PUBLISHED" and row["published_at"]:
            stamp = row["published_at"]
        else:
            stamp = row["scheduled_at"] or row["created_at"]
        when = _parse_utc(stamp)
        if when:
            times[row["account"]].append(when)
    return times


def _auto_pilot_backoff(video_id: str) -> None:
    attempts = _auto_pilot_retry.get(video_id, (0, 0))[0]
    wait = _AUTO_PILOT_BACKOFF_SECS[min(attempts, len(_AUTO_PILOT_BACKOFF_SECS) - 1)]
    _auto_pilot_retry[video_id] = (attempts + 1, time.time() + wait)


def _auto_pilot_publish(settings: dict, config: dict) -> None:
    """Schedule at most one approved video per pass.

    One, because the upload runs here and blocks the loop for about a minute;
    the next tick takes the next video.
    """
    api_key = _publishing_key()
    if not api_key:
        return
    projects = list(config["projects"])
    with db.conn(DB_PATH) as con:
        videos = [dict(r) for r in con.execute(
            "SELECT id, project_id, title, topic, publish_title, publish_description"
            " FROM videos WHERE status = 'VIDEO_APPROVED' AND archived_at IS NULL"
            " AND auto_pilot_hold = 0 AND project_id IN (%s) ORDER BY updated_at ASC"
            % ",".join("?" * len(projects)), projects)]
        allowed = set(pipeline._allowed_account_ids(con))
    limits = config["account_limits"]
    # The allowlist is re-checked here, not only when the configuration was
    # saved: it can change afterwards.
    targets = {
        pid: [a for a in ids
              if a in allowed and limits.get(a, pipeline.AUTO_PILOT_DEFAULT_DAILY) > 0]
        for pid, ids in config["projects"].items()}
    now_ts = time.time()
    # A video with nowhere to post is dropped before postforme is asked
    # anything. Waiting at VIDEO_APPROVED is a supported state that can last
    # indefinitely, and this runs every tick.
    videos = [v for v in videos if targets[v["project_id"]]
              and _auto_pilot_retry.get(v["id"], (0, 0))[1] <= now_ts]
    if not videos:
        return

    try:
        connected = {a["id"] for a in postforme.list_accounts(api_key)}
    except postforme.PostformeError as e:
        log.warning(f"Auto Pilot publish deferred: {e}")
        return

    for video in videos:
        video_id = video["id"]
        # An account disconnected upstream since it was chosen is dropped too.
        account_ids = [a for a in targets[video["project_id"]] if a in connected]
        if not account_ids:
            continue

        zone_name, zone = _auto_pilot_zone()
        now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)
        posts = _account_post_times(account_ids)
        slot_at = autopilot.next_slot(
            now, zone, dt.timedelta(minutes=settings["auto_pilot_gap_mins"]),
            [{"limit": limits.get(a, pipeline.AUTO_PILOT_DEFAULT_DAILY), "posts": posts[a]}
             for a in account_ids])
        if slot_at is None:
            log.warning(f"[{video_id}] Auto Pilot found no free slot within a year",
                        extra={"video_id": video_id})
            _auto_pilot_backoff(video_id)
            continue
        slot = None
        if slot_at > now:
            slot = (slot_at.strftime("%Y-%m-%dT%H:%M:%SZ"), zone_name,
                    slot_at.astimezone(zone).strftime("%Y-%m-%d %H:%M"))

        title, description = pipeline.publish_text(video)
        payload, code = pipeline.start_publish(
            DB_PATH, api_key, video_id, account_ids, title, description, {}, slot=slot)
        if code == 201:
            _auto_pilot_retry.pop(video_id, None)
            _comment(video_id, "This post was started by Auto Pilot. No human reviewed "
                               "the video or its title and description.")
            log.info(f"[{video_id}] Auto Pilot {'scheduled' if slot else 'published'}",
                     extra={"video_id": video_id})
        elif not payload.get("reconciling"):
            # start_publish comments on its own 502s; a refusal before the
            # claim (no rendered file, say) leaves no trace unless noted here.
            if code < 500 and code != 409 and video_id not in _auto_pilot_retry:
                _comment(video_id, f"Auto Pilot could not publish this video: "
                                   f"{payload.get('error', 'unknown error')}")
            _auto_pilot_backoff(video_id)
        return


def _poll_video_metrics() -> None:
    """Hourly snapshot pass, delegating to metrics.poll.

    Polled and cached rather than fetched on page load: an analytics page
    reading live would depend on postforme being up and fast, and the snapshots
    have to be captured continuously regardless — a time series only contains
    what something recorded at the time.

    Shared with the dashboard's Refresh buttons (renderer/api/metrics.py) so
    both go through the same per-account walk. An earlier per-publication
    version silently lost snapshots past the fifth target, because postforme
    allows 5 requests/second and the 429s were caught and skipped.
    """
    api_key = _publishing_key()
    if not api_key:
        return
    if not _metrics_due():
        return
    # Stamped before the work, not after: a pass that dies partway must not
    # retry on the very next loop iteration 20 seconds later.
    with db.conn(DB_PATH) as con:
        con.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?)"
            " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_METRICS_STAMP_KEY, db._now()))

    result = metrics.poll(DB_PATH, api_key)
    if result["snapshots"] or result["errors"]:
        log.info(f"metrics: {result['snapshots']} snapshot(s) across "
                 f"{result['accounts']} account(s), {result['errors']} error(s)")


# ── Retention (TMDEV-84) ────────────────────────────────────────────────────
#
# Deletes the mp4 and job dir of videos published more than retention_days ago
# and archives their rows, via the same pipeline.archive_video the dashboard's
# DELETE uses. Here because this is the only continuously running process with
# both DB and filesystem access — poll.py has no DB access by design.
#
# retention_days sweeps PUBLISHED videos, dated from their latest publication.
# Anything that ages out unpublished still has an mp4 that cost real ElevenLabs
# and render time, unrecoverably — so FAILED and TOPIC_REJECTED are swept only
# under their own key, unpublished_retention_days, which is off by default and
# dates them from updated_at, when they last moved (TMDEV-134). The two passes
# are independent: either key at 0 turns off its own pass only.
# Throttled with a settings-row stamp for the same reason metrics are.
_RETENTION_INTERVAL_SECS = 3600
_RETENTION_STAMP_KEY = "last_retention_sweep_at"


def _retention_days(key: str = "retention_days") -> int:
    default = int(pipeline.SETTINGS_SPEC[key][1])
    try:
        days = int(_setting(key, str(default)))
    except (ValueError, TypeError):
        return default
    if not pipeline.MIN_RETENTION_DAYS <= days <= pipeline.MAX_RETENTION_DAYS:
        return default
    return days


def _retention_due() -> bool:
    stamp = _setting(_RETENTION_STAMP_KEY, "")
    if not stamp:
        return True
    try:
        last = calendar.timegm(time.strptime(stamp, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return True
    return time.time() - last >= _RETENTION_INTERVAL_SECS


def _force_retention_due(db_path: str) -> None:
    """Test seam: clear the rate-limit stamp so the next pass sweeps again."""
    with db.conn(db_path) as con:
        con.execute("DELETE FROM settings WHERE key = ?", (_RETENTION_STAMP_KEY,))


def _sweep_retention() -> None:
    """One retention pass. Never raises.

    Wrapped because main() has no error handling of its own: an escaping
    exception restarts the container, and _reconcile_rendering_videos counts
    that restart as a render failure against whatever video was rendering —
    with max_render_retries at 1, two of them FAIL an unrelated video.
    """
    try:
        _sweep_retention_once()
    except Exception:  # noqa: BLE001 - see docstring
        log.exception("retention sweep failed")


def _cutoff(days: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - days * 86400))


def _sweep_retention_once() -> None:
    days = _retention_days()
    unpublished_days = _retention_days("unpublished_retention_days")
    if (days == 0 and unpublished_days == 0) or not _retention_due():
        return
    with db.conn(DB_PATH) as con:
        con.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (_RETENTION_STAMP_KEY, db._now()))
    if days:
        _sweep_published(days)
    if unpublished_days:
        _sweep_unpublished(unpublished_days)


def _sweep_published(days: int) -> None:
    cutoff = _cutoff(days)
    with db.conn(DB_PATH) as con:
        # Keyed on when the video was published, not created_at or updated_at.
        # published_at is NOT NULL DEFAULT '', so the '' filter is what stops a
        # row with no real timestamp reading as infinitely old; a video with no
        # usable publish time gets a NULL MAX and is never swept.
        rows = con.execute(
            "SELECT v.id FROM videos v"
            " WHERE v.status = 'PUBLISHED' AND v.archived_at IS NULL"
            "   AND (SELECT MAX(p.published_at) FROM video_publications p"
            "        WHERE p.video_id = v.id AND p.status = 'PUBLISHED'"
            "          AND p.published_at != '') < ?",
            (cutoff,)).fetchall()
    for row in rows:
        video_id = row["id"]
        try:
            out = pipeline.archive_video(
                DB_PATH, video_id, {"PUBLISHED"}, "agent",
                f"Archived by retention: published more than {days} day(s) ago, so the "
                f"rendered video and its working files were deleted. Publication links "
                f"and analytics are kept.")
            if out["result"] == "archived":
                log.info(f"[{video_id}] archived by retention", extra={"video_id": video_id})
        except Exception:  # noqa: BLE001 - one bad video must not stop the pass
            log.exception(f"[{video_id}] retention archive failed", extra={"video_id": video_id})


def _sweep_unpublished(days: int) -> None:
    """FAILED and TOPIC_REJECTED, dated from updated_at (TMDEV-134).

    Every row qualifies, files or not — a rejected topic that never had any is
    archived too, which moves it from the board to the Archive (user decision).
    archive_video re-checks the status and the cutoff in its own UPDATE, so a
    video retried out of FAILED, or edited (which restarts its clock), between
    this SELECT and the archive is a conflict, not a loss.
    """
    statuses = pipeline.UNPUBLISHED_RETENTION_STATUSES
    cutoff = _cutoff(days)
    with db.conn(DB_PATH) as con:
        # The '' filter mirrors the published pass: a row with no real
        # timestamp must not read as infinitely old.
        rows = con.execute(
            "SELECT id, status FROM videos"
            f" WHERE status IN ({','.join('?' * len(statuses))}) AND archived_at IS NULL"
            "   AND updated_at != '' AND updated_at < ?",
            (*sorted(statuses), cutoff)).fetchall()
    for row in rows:
        video_id = row["id"]
        try:
            out = pipeline.archive_video(
                DB_PATH, video_id, set(statuses), "agent",
                f"Archived by retention: {statuses[row['status']]} more than {days} day(s) "
                f"ago. Any rendered video and working files it had were deleted.",
                updated_before=cutoff)
            if out["result"] == "archived":
                log.info(f"[{video_id}] archived by retention", extra={"video_id": video_id})
        except Exception:  # noqa: BLE001 - one bad video must not stop the pass
            log.exception(f"[{video_id}] retention archive failed", extra={"video_id": video_id})


# ── Discord notifications (TMDEV-5) ─────────────────────────────────────────
#
# A sweep rather than a send at each write site. The three notifiable statuses
# are written by three different processes — TOPIC_PROPOSED by the MCP server's
# create_video, SCRIPT_READY by either the MCP server or the Flask PATCH, and
# VIDEO_READY right here — and this loop is the only place that sees all three.
# It also bundles a research run's topics for free, keeps a slow or unreachable
# Discord out of every MCP call and dashboard save, and retries a failed send
# on the next tick, because the marker below only advances on success.
NOTIFIABLE_STATUSES = ("TOPIC_PROPOSED", "SCRIPT_READY", "VIDEO_READY")

# Which setting gates which status.
_NOTIFY_SETTING = {
    "TOPIC_PROPOSED": "notify_topic_proposed",
    "SCRIPT_READY":   "notify_script_ready",
    "VIDEO_READY":    "notify_video_ready",
}

# How long the newest proposed topic must have sat before the bundle goes out.
# A research run files its topics seconds apart, and this loop ticks every 20s,
# so without a settle window one run would arrive as several messages. It is a
# debounce, not a guarantee: a run that spaces proposals more than this apart
# still produces two messages, which is an acceptable trade for not holding a
# notification indefinitely while an agent keeps working.
TOPIC_SETTLE_SECS = 120


# videos.notified_status holds an *arrival*, "<status>@<updated_at>", not just a
# status name. That difference is the whole dedupe.
#
# A status name alone is not an identity: a video going
# SCRIPT_READY -> REVISION_REQUESTED -> SCRIPT_READY entirely between two sweeps
# would still read as "already announced at SCRIPT_READY", and the human who
# asked for the revision would never hear that it landed. The window is not
# theoretical — a render holds this loop for up to forty minutes, which is
# ample time for a human to request a revision and the next cron tick's agent
# to act on it.
#
# The alternative fix is to clear the marker wherever status is written, but
# status is written by three different processes, and keeping notification
# logic out of all of them is the entire reason this is a sweep.
#
# Every status write bumps updated_at, so pairing the two makes each arrival
# distinct without any write site knowing this feature exists. The one thing it
# cannot distinguish is two status changes inside the same second, since these
# timestamps are second-granularity — which needs a human and an agent to act
# within the same second of each other.
def _ARRIVAL_SQL(prefix: str = "") -> str:
    return f"{prefix}status || '@' || {prefix}updated_at"


def _arrival(row) -> str:
    """The Python-side twin of _ARRIVAL_SQL, for a row already read."""
    return f"{row['status']}@{row['updated_at']}"


def _parse_stamp(value: str):
    """A DB UTC timestamp as epoch seconds, or None if unparseable."""
    try:
        return calendar.timegm(time.strptime(value, "%Y-%m-%dT%H:%M:%SZ"))
    except (ValueError, TypeError):
        return None


def _review_summary(feedback: str) -> str:
    """The overall verdict line of a stored AI review, for the embed.

    ai_review._format_feedback puts "**Overall:** ..." first precisely so the
    most important content survives truncation, so the first prose line is the
    verdict. The full review is pages long and already on the video; this only
    says at a glance whether the reviewer was happy.
    """
    for line in (feedback or "").splitlines():
        line = line.strip()
        # "* " and "- " with the space, never the bare character: the verdict
        # line is "**Overall:** ..." and a bare "*" test skips exactly the line
        # this is looking for.
        if line and not line.startswith(("- ", "* ", "|", "#", "> ")):
            return line
    return ""


def _sweep_notifications() -> None:
    """One Discord notification pass. Never raises — see _sweep_retention."""
    try:
        _sweep_notifications_once()
    except Exception:  # noqa: BLE001 - see _sweep_retention's docstring
        log.exception("discord notification sweep failed")


def _sweep_notifications_once() -> None:
    with db.conn(DB_PATH) as con:
        # One read of everything rather than several _setting calls: this also
        # supplies the voice roster used to name a video's voice below, and it
        # returns credentials raw, which is what the send needs (the masking in
        # pipeline.py happens at the /settings route boundary, not here).
        settings = pipeline._read_all_settings(con)

    webhook = settings.get("discord_webhook_url", "")
    enabled = {
        status: bool(settings.get(key))
        for status, key in _NOTIFY_SETTING.items()
    }
    if not webhook or not any(enabled.values()):
        # Mark, don't just skip. Videos keep reaching checkpoints while
        # notifications are off, and without this every one of them would be
        # sitting unannounced the moment a webhook is pasted in — switching the
        # feature on would fire a backlog. Same reasoning as the migration's
        # one-time backfill: enabling starts announcing from now, it does not
        # replay history.
        _mark_seen(NOTIFIABLE_STATUSES)
        return

    base_url = settings.get("dashboard_base_url", "")
    voices = {v["voice_id"]: v["name"] for v in settings.get("elevenlabs_voices", [])}

    for status in NOTIFIABLE_STATUSES:
        if not enabled[status]:
            _mark_seen([status])
            continue
        rows = _pending_notifications(status)
        if not rows:
            continue
        try:
            if status == "TOPIC_PROPOSED":
                if not _topics_settled(rows):
                    continue
                payload = discord_notify.build_topics_payload(rows, base_url=base_url)
                discord_notify.send(webhook, payload)
                _mark_notified(rows)
                log.info(f"notified Discord of {len(rows)} proposed topic(s)")
            else:
                for row in rows:
                    payload = _payload_for(status, row, voices, base_url)
                    discord_notify.send(webhook, payload)
                    _mark_notified([row])
                    log.info(f"[{row['id']}] notified Discord of {status}",
                             extra={"video_id": row["id"]})
        except discord_notify.DiscordError as exc:
            # Marker left unadvanced on purpose — the next tick retries. The
            # message is already redacted by discord_notify.
            log.warning(f"Discord notification for {status} failed: {exc}")


def _payload_for(status: str, row: dict, voices: dict, base_url: str) -> dict:
    video = dict(row)
    if status == "SCRIPT_READY":
        video["voice_name"] = voices.get(video.get("voice_id") or "", "")
        return discord_notify.build_script_ready_payload(video, base_url=base_url)
    video["duration_secs"] = pipeline._video_duration_secs(video["id"])
    video["review_summary"] = _review_summary(video.get("gemini_feedback") or "")
    return discord_notify.build_video_ready_payload(video, base_url=base_url)


def _pending_notifications(status: str) -> list:
    """Videos that have arrived at `status` since the last notification for it."""
    with db.conn(DB_PATH) as con:
        rows = con.execute(
            "SELECT v.*, p.name AS project_name, sp.name AS script_profile_name"
            "  FROM videos v"
            "  LEFT JOIN projects p ON p.id = v.project_id"
            "  LEFT JOIN script_profiles sp ON sp.id = v.script_profile_id"
            " WHERE v.archived_at IS NULL AND v.status = ?"
            f"   AND v.notified_status != {_ARRIVAL_SQL('v.')}"
            " ORDER BY v.created_at",
            (status,)).fetchall()
    return [dict(r) for r in rows]


def _topics_settled(rows: list) -> bool:
    newest = max((_parse_stamp(r["updated_at"]) or 0) for r in rows)
    return time.time() - newest >= TOPIC_SETTLE_SECS


def _mark_notified(rows: list) -> None:
    """Record that each of these videos' current arrival has been announced.

    Guarded on updated_at: if the video moved between the SELECT and here, the
    UPDATE matches nothing and the new arrival is picked up on the next tick.
    That makes the race produce a duplicate message rather than a silent miss,
    which is the right way round — nobody notices a notification that never
    came.

    Deliberately a raw UPDATE and not db.update_fields: that helper always sets
    updated_at, and updated_at is the FIFO ordering key for the render claim.
    Notifying a video must not reorder the render queue.
    """
    with db.conn(DB_PATH) as con:
        for row in rows:
            con.execute(
                "UPDATE videos SET notified_status = ?"
                " WHERE id = ? AND updated_at = ?",
                (_arrival(row), row["id"], row["updated_at"]))


def _mark_seen(statuses: list) -> None:
    """Stamp current arrivals at `statuses` as announced, without sending.

    Used for the statuses whose trigger is off. Without it, everything that
    reached a checkpoint while notifications were disabled would still be
    pending, and enabling a trigger would fire the whole backlog at once.
    Same raw-UPDATE reasoning as above; the `!=` keeps it a no-op write when
    there is nothing to stamp, which is the common case on every tick.
    """
    if not statuses:
        return
    placeholders = ",".join("?" for _ in statuses)
    with db.conn(DB_PATH) as con:
        con.execute(
            f"UPDATE videos SET notified_status = {_ARRIVAL_SQL()}"
            f" WHERE archived_at IS NULL AND status IN ({placeholders})"
            f"   AND notified_status != {_ARRIVAL_SQL()}",
            list(statuses))


# ── Stalled VOICING backstop (TMDEV-112) ────────────────────────────────────
#
# VOICING is agent-workable, so a video no tick manages to voice is picked up
# again on every one: an agent declining generate_voice, a voicing error that
# keeps recurring, a poller that stopped running. From outside, every one of
# those looks exactly like an agent that has not run yet — nothing escalated
# and nothing reported it. This makes the stall visible: a comment on the video
# (the dashboard), an ERROR line, and a Discord alert when a webhook is set.
#
# Measured on updated_at, which every status write bumps — so it is time since
# the video last arrived at VOICING. Reported once per arrival through the same
# notified_status marker the checkpoint sweep uses. VOICING is not one of that
# sweep's statuses, so it never reads or stamps a VOICING arrival, and the two
# cannot collide.
#
# A paused pipeline is not a stall: poll.py exits before touching any workable
# video, so nothing is meant to voice anything. Flagging then would be a false
# alarm that also spends the arrival's one-shot marker, silencing a real stall
# after resume. Skipping is not enough on its own, though — a video approved
# during a long pause is already "old" the moment the pipeline resumes, before a
# single tick has had the chance to voice it. So each paused pass stamps a
# settings row, and flagging waits the same three intervals after the last one.
VOICING_STALL_TICKS = 3
_DEFAULT_POLL_MINS = 30
_PAUSED_STAMP_KEY = "voicing_stall_paused_at"


def _poll_interval_mins() -> int:
    """How often cron runs the agent. Recorded by onboarding for visibility;
    anything unusable reads as the onboarding default."""
    try:
        mins = int(_setting("poll_interval_mins", str(_DEFAULT_POLL_MINS)))
    except (ValueError, TypeError):
        return _DEFAULT_POLL_MINS
    return mins if mins > 0 else _DEFAULT_POLL_MINS


def _sweep_stalled_voicing() -> None:
    """One stalled-VOICING pass. Never raises — see _sweep_retention."""
    try:
        _sweep_stalled_voicing_once()
    except Exception:  # noqa: BLE001 - see _sweep_retention's docstring
        log.exception("stalled-VOICING sweep failed")


def _sweep_stalled_voicing_once() -> None:
    interval_secs = _poll_interval_mins() * 60
    stall_secs = VOICING_STALL_TICKS * interval_secs
    cutoff = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - stall_secs))
    with db.conn(DB_PATH) as con:
        settings = pipeline._read_all_settings(con)
        if settings.get("pipeline_paused"):
            con.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (_PAUSED_STAMP_KEY, db._now()))
            return
        row = con.execute(
            "SELECT value FROM settings WHERE key = ?", (_PAUSED_STAMP_KEY,)).fetchone()
        paused_at = _parse_stamp(row["value"]) if row else None
        if paused_at is not None and time.time() - paused_at < stall_secs:
            return
        rows = [dict(r) for r in con.execute(
            "SELECT id, title, topic, updated_at FROM videos"
            " WHERE archived_at IS NULL AND status = 'VOICING' AND updated_at <= ?"
            f"   AND notified_status != {_ARRIVAL_SQL()}"
            " ORDER BY updated_at",
            (cutoff,)).fetchall()]
        if not rows:
            return

    webhook = settings.get("discord_webhook_url", "")
    for row in rows:
        stalled = max(0, int(time.time() - (_parse_stamp(row["updated_at"]) or time.time())))
        ago = discord_notify.elapsed(stalled)
        comment = (
            f"Stuck in VOICING: approved for voicing {ago} ago — about "
            f"{stalled // interval_secs} poll ticks — and still not voiced. Every tick "
            f"picks this video up, so something keeps failing: an error from "
            f"generate_voice, the agent declining to call it, or the poller not "
            f"running. The poll log says which.")
        if not _flag_stalled(row, comment):
            continue
        log.error(f"[{row['id']}] stuck in VOICING for {ago} — not voiced after "
                  f"{VOICING_STALL_TICKS}+ poll intervals", extra={"video_id": row["id"]})
        # Discord goes out whenever a webhook is set, whatever the per-checkpoint
        # toggles say: those pick which routine checkpoints to announce, and this
        # is the pipeline being stuck. A failed send is not retried — the comment
        # is the record, and retrying would mean re-flagging, i.e. a duplicate
        # comment every pass for as long as Discord is down.
        if webhook:
            try:
                discord_notify.send(webhook, discord_notify.build_voicing_stalled_payload(
                    {**row, "stalled_secs": stalled},
                    base_url=settings.get("dashboard_base_url", "")))
            except discord_notify.DiscordError as exc:
                log.warning(f"[{row['id']}] Discord stalled-VOICING alert failed: {exc}",
                            extra={"video_id": row["id"]})


def _flag_stalled(row: dict, comment: str) -> bool:
    """Record this VOICING arrival as reported, and comment on the video.

    One transaction, guarded on updated_at and status like _mark_notified: if the
    video was voiced (or moved at all) since it was read, nothing is written and
    there is nothing to report. Raw UPDATE for the same reason as there — flagging
    a video must not bump updated_at, which is the very clock being measured.
    """
    with db.conn(DB_PATH) as con:
        cur = con.execute(
            "UPDATE videos SET notified_status = ?"
            " WHERE id = ? AND status = 'VOICING' AND updated_at = ?"
            "   AND archived_at IS NULL",
            (f"VOICING@{row['updated_at']}", row["id"], row["updated_at"]))
        if cur.rowcount == 0:
            return False
        con.execute(
            "INSERT INTO comments (video_id, author, content, created_at)"
            " VALUES (?, 'agent', ?, ?)",
            (row["id"], comment, db._now()))
    return True


def _reconcile_rendering_videos() -> None:
    """On startup, requeue (or fail) any video stuck in RENDERING.

    These are videos whose render was interrupted by a worker crash/restart.
    Mirrors the normal render-crash backstop (_handle_render_failure): each
    reconciliation atomically increments render_fail_count and escalates
    straight to FAILED once it exceeds max_render_retries, instead of
    unconditionally retrying forever — otherwise a render that reliably
    crashes the worker (e.g. OOM) loops RENDERING -> restart -> RENDER_QUEUED
    -> RENDERING forever and never reaches the FAILED backstop.

    Requeues to RENDER_QUEUED (not REVISION_REQUESTED) so the worker retries
    automatically without needing the agent — an improvement over the old
    in-Flask design, where a restart always bounced the video back to the
    agent even though nothing about the render itself was wrong.
    """
    try:
        with db.conn(DB_PATH) as con:
            rows = con.execute("SELECT id FROM videos WHERE status = 'RENDERING'").fetchall()
    except Exception as e:
        log.error(f"startup reconcile check failed: {e}")
        return

    if not rows:
        return

    max_retries = _max_render_retries()
    for row in rows:
        video_id = row["id"]
        try:
            with db.conn(DB_PATH) as con:
                con.execute(
                    "UPDATE videos SET render_fail_count = render_fail_count + 1, updated_at = ? WHERE id = ?",
                    (db._now(), video_id),
                )
                count_row = con.execute(
                    "SELECT render_fail_count FROM videos WHERE id = ?", (video_id,)
                ).fetchone()
                fail_count = count_row["render_fail_count"] if count_row else 1

            if fail_count > max_retries:
                db.add_comment(DB_PATH, video_id, "agent",
                                f"Render interrupted by worker restart {fail_count} times "
                                f"(limit {max_retries}) — giving up.")
                db.set_status(DB_PATH, video_id, "FAILED", only_if="RENDERING")
            else:
                db.add_comment(DB_PATH, video_id, "agent",
                                "Render interrupted by worker restart — automatically re-queued.")
                db.set_status(DB_PATH, video_id, "RENDER_QUEUED", only_if="RENDERING")
        except Exception as exc:
            log.error(f"failed to reconcile video {video_id}: {exc}", extra={"video_id": video_id})

    log.info(f"startup: reconciled {len(rows)} interrupted RENDERING video(s)")


def _claim_next() -> str | None:
    """Atomically claim the oldest RENDER_QUEUED video. Returns its id, or None if idle."""
    try:
        with db.conn(DB_PATH) as con:
            row = con.execute(
                "SELECT id FROM videos WHERE status = 'RENDER_QUEUED' ORDER BY updated_at ASC, id ASC LIMIT 1"
            ).fetchone()
    except Exception as e:
        log.error(f"claim query failed: {e}")
        return None
    if not row:
        return None
    video_id = row["id"]
    # Guarded in the UPDATE's own WHERE clause (not SELECT-then-compare) —
    # the same atomic-claim pattern used throughout the pipeline. With a
    # single worker process this never actually loses a race, but it's the
    # same defensive shape as submit_render's claim.
    if db.set_status(DB_PATH, video_id, "RENDERING", only_if="RENDER_QUEUED"):
        return video_id
    return None


def _stage_and_render(video_id: str) -> None:
    """Render one already-claimed (status=RENDERING) video: stage its job
    files into the Remotion public dir, invoke Remotion, then run the tail."""
    with db.conn(DB_PATH) as con:
        row = con.execute(
            "SELECT project_id, voice_file_path, timeline_path, scene_config_path FROM videos WHERE id = ?",
            (video_id,),
        ).fetchone()
    if not row:
        log.error(f"[{video_id}] video row disappeared after claim — skipping", extra={"video_id": video_id})
        return

    # Every location is derived from the ids, never read from the row's path
    # columns (TMDEV-162): those were once writable through PATCH and
    # update_video, so a row tampered with before the fix could name any file
    # the worker can read, and it would be staged into the render. The columns
    # still say whether each file was written.
    try:
        audio_path = tjobs.job_file(pipeline.JOBS_DIR, video_id, tjobs.AUDIO)
        timeline_path = tjobs.job_file(pipeline.JOBS_DIR, video_id, tjobs.TIMELINE)
        scene_config_path = tjobs.job_file(pipeline.JOBS_DIR, video_id, tjobs.SCENE_CONFIG)
        images_dir = tjobs.images_dir(pipeline.JOBS_DIR, video_id)
        output_file = tjobs.output_file(OUTPUT_DIR, row["project_id"], video_id)
    except tjobs.UnsafePath as e:
        # Not something a revision can fix, and retrying renders the same
        # refusal, so it goes straight to FAILED for a human to look at.
        log.error(f"[{video_id}] refusing to render: {e}", extra={"video_id": video_id})
        db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
            f"Render refused, moved to FAILED: {e}. The video's id or its project's id "
            "cannot be used as a file path, so nothing was staged or rendered."))
        db.set_status(DB_PATH, video_id, "FAILED", only_if="RENDERING")
        return

    missing = [
        name for name, written, p in [
            ("voice_file_path", row["voice_file_path"], audio_path),
            ("timeline_path", row["timeline_path"], timeline_path),
            ("scene_config_path", row["scene_config_path"], scene_config_path),
        ] if not written or not p.is_file()
    ]
    if missing:
        db.add_comment(DB_PATH, video_id, "agent", f"Render failed: missing job file(s): {missing}")
        db.set_status(DB_PATH, video_id, "REVISION_REQUESTED", only_if="RENDERING")
        return

    public_dir = REMOTION_DIR / "public" / video_id
    public_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(scene_config_path, public_dir / tjobs.SCENE_CONFIG)
    shutil.copy(timeline_path, public_dir / tjobs.TIMELINE)
    shutil.copy(audio_path, public_dir / tjobs.AUDIO)

    # Per-video generated images (TMDEV-29). Optional — most videos have none,
    # so this must stay out of the `missing` precondition list above. Scenes
    # reference these as /public/<video_id>/images/<name>, which is exactly what
    # staticFile() would resolve to; validate_job checks they exist first.
    # Symlinks are skipped: copytree follows them, so a planted link would copy
    # whatever it points at into the render.
    if images_dir.is_dir():
        shutil.copytree(images_dir, public_dir / tjobs.IMAGES, dirs_exist_ok=True,
                        ignore=tjobs.ignore_symlinks)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_path = str(output_file)

    props = json.dumps({
        "sceneConfigPath": f"/public/{video_id}/scene-config.json",
        "timelinePath": f"/public/{video_id}/timeline.json",
        "audioPath": f"/public/{video_id}/audio.mp3",
        # From the settings table, never from scene-config.json: the agent
        # authors that file, and the watermark must not be the agent's to drop.
        "watermark": _setting("watermark_enabled", "true").lower() == "true",
    })

    timeout_secs = _render_timeout_secs()
    log.info(f"[{video_id}] rendering -> {output_path}", extra={"video_id": video_id})
    try:
        # start_new_session=True puts npx and everything it spawns (node,
        # Chromium, ffmpeg) in one new process group. subprocess.run's own
        # timeout only kills the direct child it started — any grandchildren
        # (Chromium, ffmpeg) survive, get reparented to this container's PID 1
        # (this same worker process), and keep running invisibly until they
        # finish on their own, competing with whatever render claims the video
        # next (TMDEV-57, confirmed live: a timed-out render left <defunct>
        # Chromium/ffmpeg processes and an orphaned temp file behind). Using
        # Popen directly so a killpg on the whole group is possible here.
        proc = subprocess.Popen(
            [
                "npx", "remotion", "render", "Composition", output_path,
                "--props", props,
                "--browser-executable-path", CHROMIUM_BIN,
            ],
            cwd=str(REMOTION_DIR),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        try:
            stdout, stderr = proc.communicate(timeout=timeout_secs)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()  # reaps our direct child (npx)
            # killpg's SIGKILL hits the whole group at once, but grandchildren
            # (node, chrome-headless, ffmpeg, ...) reparent to this container's
            # PID 1 -- this same worker process, per the comment above -- the
            # instant their own parent dies, before proc.wait() can claim them
            # by PID. Confirmed live (TMDEV-57 follow-up): SIGKILL guarantees
            # they'll all exit but not instantly -- heavier processes (a
            # Chromium instance tearing down many threads) can take noticeably
            # longer to actually finish than the lightweight npx wrapper
            # proc.wait() above already reaped. A non-blocking WNOHANG drain
            # right here races ahead of that and finds nothing (confirmed
            # live: the trivial `sh` link died fast enough to be caught,
            # everything heavier didn't, and sat as permanent zombies since
            # nothing ever revisited reaping). Block instead: wait() for each
            # already-reparented child in turn -- bounded by SIGKILL itself
            # guaranteeing they all eventually exit -- until none remain.
            try:
                while True:
                    os.waitpid(-1, 0)
            except ChildProcessError:
                pass
            raise
        result = subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        log.error(f"[{video_id}] render timed out after {timeout_secs}s", extra={"video_id": video_id})
        # A hung Chromium is environmental, not something the agent can fix
        # by revising the scene — auto-retry via RENDER_QUEUED (same terminal
        # choice as the crash-reconcile path above) rather than bouncing to
        # the agent as REVISION_REQUESTED.
        _handle_render_failure(video_id, f"Render timed out after {timeout_secs}s",
                                retry_status="RENDER_QUEUED")
        return

    if result.returncode == 0:
        log.info(f"[{video_id}] render complete -> {output_path}", extra={"video_id": video_id})
        _handle_render_success(video_id, output_path)
    else:
        error_msg = result.stderr or result.stdout
        log.error(f"[{video_id}] render failed: {error_msg}", extra={"video_id": video_id})
        _handle_render_failure(video_id, error_msg)


def _handle_render_success(video_id: str, output_path: str) -> None:
    try:
        db.update_fields(DB_PATH, video_id, video_path=output_path)

        # Keep the "false" in sync with pipeline.py SETTINGS_SPEC (TMDEV-165).
        gemini_review_enabled = _setting("gemini_review_enabled", "false").lower() == "true"
        gemini_api_key = _setting("gemini_api_key", "")

        if not gemini_review_enabled or not gemini_api_key:
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
            return

        max_review_loops = _max_ai_review_loops()

        # Atomically increment ai_review_count
        with db.conn(DB_PATH) as con:
            con.execute(
                "UPDATE videos SET ai_review_count = ai_review_count + 1, updated_at = ? WHERE id = ?",
                (db._now(), video_id),
            )
            row = con.execute(
                "SELECT ai_review_count, script, tts_text, visual_style, "
                "resolved_visual_style FROM videos WHERE id = ?", (video_id,)
            ).fetchone()
            new_count = row["ai_review_count"] if row else 1
            # VQA-6: the review's pronunciation reference. script is the
            # authored wording the captions show; tts_text is what was
            # actually sent to ElevenLabs (empty on rows voiced before that
            # column existed — the review degrades to the script alone).
            script_text = (row["script"] if row else "") or ""
            tts_text = (row["tts_text"] if row else "") or ""
            # TMDEV-101: the canvas the video was deliberately painted on, and
            # whether it may contain figures, so the reviewer judges it against
            # its own intended look. The two are independent — an "auto" video
            # can be dark AND full of held, discretely-posed figures — so they
            # are passed separately rather than as one register name. A blank
            # canvas means "auto" never settled, which the prompt handles by
            # stating no contract at all rather than assuming one.
            raw_style = (row["visual_style"] if row else "") or ""
            canvas = pipeline.effective_canvas(
                raw_style, (row["resolved_visual_style"] if row else "") or "")
            has_figures = pipeline.figures_allowed(raw_style)
            # Narrower than has_figures: "illustrated" has figures but they are
            # generated artwork, so the reviewer must not be told that simple
            # line art is intended there.
            has_line_art = pipeline.line_art_allowed(raw_style)

        over_cap = new_count > max_review_loops

        # Load scene-config for the review prompt (staged into the public dir above)
        scene_config_path = REMOTION_DIR / "public" / video_id / "scene-config.json"
        if not scene_config_path.exists():
            db.add_comment(DB_PATH, video_id, "agent",
                            "scene-config.json not found — skipping AI review, advancing to VIDEO_READY.")
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
            return

        with open(scene_config_path) as fh:
            scene_config_dict = json.load(fh)

        # Runs even when over_cap — TMDEV-58: the render that actually ships still gets a fresh
        # review instead of shipping with the previous round's stale gemini_feedback.
        # ai_review.py is deliberately DB-free, so the settings-table values
        # are read here and passed in rather than looked up in there (VQA-7).
        result_review = ai_review.run_ai_review(output_path, scene_config_dict,
                                                 script_text=script_text, tts_text=tts_text,
                                                 model=_setting("ai_review_model", "gemini-2.5-flash"),
                                                 fps=_setting("ai_review_fps", "10"),
                                                 api_key=gemini_api_key,
                                                 canvas=canvas,
                                                 figures=has_figures,
                                                 line_art=has_line_art)
        # Every paid review is recorded — a second loop costs a second row, and
        # a reply that failed to parse was still billed (TMDEV-107).
        review_usage = result_review.get("usage")
        if review_usage:
            tusage.record_usage(DB_PATH, service="gemini",
                                model=review_usage.get("model") or "", operation="ai_review",
                                units=tusage.gemini_units(review_usage.get("usageMetadata")),
                                raw=review_usage, videos=[video_id])
        feedback = result_review.get("feedback") or ""
        db.update_fields(DB_PATH, video_id, gemini_feedback=feedback)

        must_fix = result_review.get("must_fix") or []
        suggestions = result_review.get("suggestions") or []

        if "error" in result_review:
            # Routing first, error second. Every other branch below already
            # leads with what happened to the video; this one used to end with
            # it, so a long Gemini error (httpx embeds the whole request URL)
            # truncated the "advancing to VIDEO_READY" clause away and left a
            # comment that never said where the video went.
            db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
                f"AI review failed — advancing to VIDEO_READY. "
                f"Error: {result_review['error'] or ''}"))
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
        elif over_cap:
            db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
                f"Max AI reviews ({max_review_loops}) reached — accepting as VIDEO_READY "
                f"regardless of findings:\n{feedback}"))
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
        elif must_fix or suggestions:
            db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
                f"AI review {new_count} of {max_review_loops} found {len(must_fix)} "
                f"must-fix, {len(suggestions)} suggestions:\n{feedback}"))
            db.set_status(DB_PATH, video_id, "REVISION_REQUESTED", only_if="RENDERING")
        else:
            db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
                f"AI review {new_count} of {max_review_loops} — clean: {feedback}"))
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
    except Exception as exc:
        log.error(f"[{video_id}] unexpected error in render tail: {exc}", extra={"video_id": video_id})
        try:
            db.add_comment(DB_PATH, video_id, "agent", f"Unexpected error in render tail: {exc}")
        except Exception:
            pass
        try:
            db.set_status(DB_PATH, video_id, "REVISION_REQUESTED", only_if="RENDERING")
        except Exception as exc2:
            log.error(f"[{video_id}] also failed to set REVISION_REQUESTED: {exc2}", extra={"video_id": video_id})


def _handle_render_failure(video_id: str, error_msg: str, retry_status: str = "REVISION_REQUESTED") -> None:
    """Increment render_fail_count; escalate to FAILED past the cap, else
    move to retry_status (REVISION_REQUESTED for a real render crash — the
    agent likely needs to fix something; RENDER_QUEUED for a timeout — see
    the caller in _stage_and_render)."""
    error_msg = _truncate_comment(error_msg)
    try:
        # Atomically increment render_fail_count — capped by max_render_retries
        # so a persistently crashing render doesn't cycle forever with no
        # backstop. Since VQA-7 that key caps render retries ONLY; the AI
        # review loop has its own (ai_review_max_loops).
        with db.conn(DB_PATH) as con:
            con.execute(
                "UPDATE videos SET render_fail_count = render_fail_count + 1, updated_at = ? WHERE id = ?",
                (db._now(), video_id),
            )
            row = con.execute("SELECT render_fail_count FROM videos WHERE id = ?", (video_id,)).fetchone()
            fail_count = row["render_fail_count"] if row else 1

        max_render_retries = _max_render_retries()

        if fail_count > max_render_retries:
            db.add_comment(DB_PATH, video_id, "agent",
                            f"Render failed {fail_count} times (limit {max_render_retries}) — "
                            f"giving up. Last error: {error_msg}")
            db.set_status(DB_PATH, video_id, "FAILED", only_if="RENDERING")
        else:
            db.add_comment(DB_PATH, video_id, "agent", f"Render failed: {error_msg}")
            db.set_status(DB_PATH, video_id, retry_status, only_if="RENDERING")
    except Exception as exc:
        log.error(f"[{video_id}] failed to update DB after render failure: {exc}", extra={"video_id": video_id})


def main() -> None:
    # Mirrors entrypoint.sh's umask — keeps every file the worker writes into
    # the bind-mounted /output_videos host-writable/deletable.
    os.umask(0)
    pipeline._init_db(DB_PATH)
    # Adds a JSONL file handler *alongside* the stdout one configured above —
    # `docker compose logs tubematic-renderer` has to keep working unchanged.
    # A missing or unwritable /logs leaves this a no-op.
    tlog.setup_json_logging(
        "renderer", LOG_DIR,
        retention_days=pipeline.log_retention_days(DB_PATH),
        secrets=pipeline.log_secret_provider(DB_PATH),
    )
    log.info("render worker starting")
    _reconcile_rendering_videos()

    while True:
        # Both passes are non-blocking and run before the render claim, so
        # publishing can never starve rendering — and a render, which holds
        # this loop for ~20 minutes, never stalls a publish for longer than
        # one render.
        _poll_publishing_videos()
        # Before the notification sweep, so a checkpoint Auto Pilot approves
        # never also sends a "waiting for you" message.
        _sweep_auto_pilot()
        _poll_video_metrics()
        _sync_prices_if_due()
        _sweep_retention()
        _sweep_notifications()
        _sweep_stalled_voicing()

        video_id = _claim_next()
        if video_id:
            _stage_and_render(video_id)
        else:
            time.sleep(POLL_INTERVAL_SECS)


if __name__ == "__main__":
    main()
