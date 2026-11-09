"""What happens to a video when a render ends: the server side of rendering.

A renderer (the built-in one or a remote host) never reads the database. It
renders what the render gateway hands it and reports back; the rules that
move the video afterwards live here and run in main's processes only:

- the render gateway (render_gateway.py, in tubematic-api) routes a failed,
  stalled or timed-out render through after_render_failure, and re-queues
  every render a restarted renderer left behind (requeue_interrupted);
- tubematic-worker (worker.py) runs the AI review tail on an uploaded render
  (finish_render) in its review thread, and re-queues a render whose renderer
  stopped heartbeating (requeue_interrupted again).

These used to be render_agent.py's, when the renderer read SQLite itself; the
behaviour and every comment text are unchanged, so a human reading a video's
comment thread sees the same words whichever machine rendered it.

Module-level paths come from the same environment variables the renderer and
the API use. One process, one database: the gateway is created with the same
TUBEMATIC_DB this module reads.
"""
import json
import logging
import os
from pathlib import Path

import ai_review
import db
import pipeline
from tubematic_core import jobfiles as tjobs
from tubematic_core import renderers
from tubematic_core import usage as tusage

DB_PATH = os.getenv("TUBEMATIC_DB", "/data/tubematic.db")
JOBS_DIR = Path(os.getenv("TUBEMATIC_JOBS_DIR", "/jobs"))
OUTPUT_DIR = Path(os.getenv("OUTPUT_BASE_PATH", "/output_videos"))

log = logging.getLogger("render_results")

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

# What a restarted renderer's interrupted render, and one whose renderer
# stopped reporting, say on the video. The FAILED variant past the retry cap
# reuses the text before " — automatically re-queued." (requeue_interrupted).
RESTART_COMMENT = "Render interrupted by renderer restart — automatically re-queued."
UPGRADE_COMMENT = "Render interrupted by the upgrade — automatically re-queued."
_REQUEUED_SUFFIX = " — automatically re-queued."


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


def max_render_retries() -> int:
    try:
        return int(_setting("max_render_retries", "1"))
    except (ValueError, TypeError):
        return 1


def max_ai_review_loops() -> int:
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


def render_timeout_secs() -> int:
    """The absolute ceiling on one render. Keep the default in sync with
    pipeline.py SETTINGS_SPEC."""
    try:
        return int(_setting("render_timeout_secs", "10800"))
    except (ValueError, TypeError):
        return 10800


def render_stall_timeout_secs() -> int:
    """How long Remotion's progress counter may stand still before the render
    is judged hung. Keep the default in sync with pipeline.py SETTINGS_SPEC."""
    try:
        return int(_setting("render_stall_timeout_secs", "600"))
    except (ValueError, TypeError):
        return 600


def watermark_enabled() -> bool:
    """From the settings table, never from scene-config.json: the agent
    authors that file, and the watermark must not be the agent's to drop."""
    return _setting("watermark_enabled", "true").lower() == "true"


def scene_config_is_cartoon3d(scene_config_path) -> bool:
    """Whether the written scene-config renders a Cartoon 3D world: one
    generated scene whose props carry `cartoon3d` (the beats). Keep the key
    in sync with mcp/cartoon.py's CARTOON_PROPS."""
    try:
        config = json.loads(Path(scene_config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    scenes = config.get("scenes") if isinstance(config, dict) else None
    return isinstance(scenes, list) and any(
        isinstance(s, dict) and isinstance(s.get("props"), dict) and isinstance(s["props"].get("cartoon3d"), dict)
        for s in scenes)


def video_scene_is_cartoon3d(video_id: str) -> bool:
    """scene_config_is_cartoon3d for a video's job-dir scene-config; False for
    an id that cannot be a path (its refusal is the claim's to make)."""
    try:
        return scene_config_is_cartoon3d(tjobs.job_file(JOBS_DIR, video_id, tjobs.SCENE_CONFIG))
    except tjobs.UnsafePath:
        return False


def fail_without_gpu(video_id: str, cartoon: bool, render_error: str | None = None) -> None:
    """Move a GPU-only video (Cartoon 3D, or one with a mascot) straight to
    FAILED because no renderer's GPU can take it, naming every renderer and
    its GPU state. After a render on the GPU failed and the renderer's re-test
    found the GPU gone (`render_error` is then that render's error, maybe "");
    `render_error` None says nothing was rendered."""
    try:
        with db.conn(DB_PATH) as con:
            reason = renderers.gpu_unavailable_reason(con)
    except Exception as exc:  # noqa: BLE001 — the comment must still be written
        reason = f"The renderers' GPU state could not be read: {exc}."
    lead = ("Not rendered, moved to FAILED" if render_error is None else "Render failed, moved to FAILED")
    render_error = (render_error or "").strip()
    db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
        f"{lead}: this video {'is Cartoon 3D' if cartoon else 'has a mascot'}, "
        f"which renders on the GPU only. {reason}"
        " Configure or fix the GPU (python onboard.py --step gpu; Test GPU on the dashboard "
        "Settings page), then create the video again." +
        (f" The render's error: {render_error}" if render_error else "")))
    db.set_status(DB_PATH, video_id, "FAILED", only_if="RENDERING")


def after_render_failure(video_id: str, error_msg: str, retry_status: str, on_gpu: bool,
                         needs_gpu: bool, cartoon: bool, gpu_ok) -> None:
    """Route a render that failed or hung.

    The renderer re-tests a GPU a render ran on before it reports, and sends
    the answer as `gpu_ok`. A GPU-only video whose GPU no longer works goes
    straight to FAILED with the renderers' GPU state, spending no retry and no
    agent session, since neither a requeue nor the agent can bring a GPU back.
    Anything else — a GPU that still works, an unanswered re-test (None), a
    render on the CPU — is the video's own failure and takes the usual path."""
    if needs_gpu and on_gpu and gpu_ok is False:
        fail_without_gpu(video_id, cartoon, error_msg or "")
        return
    handle_render_failure(video_id, error_msg, retry_status=retry_status)


def handle_render_failure(video_id: str, error_msg: str, retry_status: str = "REVISION_REQUESTED") -> None:
    """Increment render_fail_count; escalate to FAILED past the cap, else
    move to retry_status (REVISION_REQUESTED for a real render crash — the
    agent likely needs to fix something; RENDER_QUEUED for a stall, a timeout
    or a renderer error)."""
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

        max_retries = max_render_retries()

        if fail_count > max_retries:
            db.add_comment(DB_PATH, video_id, "agent",
                           f"Render failed {fail_count} times (limit {max_retries}) — "
                           f"giving up. Last error: {error_msg}")
            db.set_status(DB_PATH, video_id, "FAILED", only_if="RENDERING")
        else:
            db.add_comment(DB_PATH, video_id, "agent", f"Render failed: {error_msg}")
            db.set_status(DB_PATH, video_id, retry_status, only_if="RENDERING")
    except Exception as exc:
        log.error(f"[{video_id}] failed to update DB after render failure: {exc}", extra={"video_id": video_id})


def requeue_interrupted(video_id: str, reason_comment: str, renderer_id: str | None = None,
                        lease_expired_before: str | None = None) -> bool:
    """Re-queue a render that never reported back: its renderer restarted, or
    stopped heartbeating until its lease ran out, or it was in flight across
    an upgrade. Returns whether the video was moved.

    Counts a render retry, like a crash: a render that reliably kills its
    renderer (an OOM) would otherwise loop RENDERING -> restart ->
    RENDER_QUEUED forever and never reach the FAILED backstop. Past
    max_render_retries the video goes to FAILED with "<reason> N times
    (limit M) — giving up.", where <reason> is reason_comment before
    " — automatically re-queued."; under it, back to RENDER_QUEUED with
    reason_comment, so the next renderer retries it with no agent involved.

    One guarded statement: the row must still be RENDERING with nothing
    uploaded (an uploaded render is the review's, never re-rendered), held by
    `renderer_id` when given, and — with `lease_expired_before` — still past
    its lease (or held by no one), so a heartbeat that extended the lease
    after the caller looked wins. Clears the claim columns either way."""
    max_retries = max_render_retries()
    where = "id = ? AND status = 'RENDERING' AND render_uploaded_at = ''"
    params: list = [video_id]
    if renderer_id is not None:
        where += " AND renderer_id = ?"
        params.append(renderer_id)
    if lease_expired_before is not None:
        where += " AND (renderer_id = '' OR render_lease_until < ?)"
        params.append(lease_expired_before)
    now = db._now()
    with db.conn(DB_PATH) as con:
        cur = con.execute(
            "UPDATE videos SET render_fail_count = render_fail_count + 1, renderer_id = '', "
            "render_lease_until = '', render_started_at = '', render_uploaded_at = '', updated_at = ? "
            f"WHERE {where}", [now, *params])
        if cur.rowcount == 0:
            return False
        fail_count = con.execute("SELECT render_fail_count FROM videos WHERE id = ?",
                                 (video_id,)).fetchone()["render_fail_count"]
        if fail_count > max_retries:
            head = reason_comment.split(_REQUEUED_SUFFIX)[0].rstrip(". ")
            status, comment = "FAILED", f"{head} {fail_count} times (limit {max_retries}) — giving up."
        else:
            status, comment = "RENDER_QUEUED", reason_comment
        con.execute("UPDATE videos SET status = ?, updated_at = ? WHERE id = ?", (status, now, video_id))
        con.execute("INSERT INTO comments (video_id, author, content, created_at) VALUES (?, 'agent', ?, ?)",
                    (video_id, _truncate_comment(comment), now))
    log.info(f"[{video_id}] interrupted render -> {status}: {comment}", extra={"video_id": video_id})
    return True


def finish_render(video_id: str) -> None:
    """The AI review tail of an uploaded render (status RENDERING,
    render_uploaded_at set): review it if review is on, then route it to
    VIDEO_READY or REVISION_REQUESTED. Never leaves the row in RENDERING
    unless the database itself is unwritable. Restart-safe: a review the
    worker did not finish simply runs again."""
    try:
        with db.conn(DB_PATH) as con:
            path_row = con.execute("SELECT video_path FROM videos WHERE id = ?", (video_id,)).fetchone()
        output_path = (path_row["video_path"] if path_row else "") or ""

        # Keep the "false" in sync with pipeline.py SETTINGS_SPEC (TMDEV-165).
        gemini_review_enabled = _setting("gemini_review_enabled", "false").lower() == "true"
        gemini_api_key = _setting("gemini_api_key", "")

        if not gemini_review_enabled or not gemini_api_key:
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
            return

        max_review_loops = max_ai_review_loops()

        # Atomically increment ai_review_count
        with db.conn(DB_PATH) as con:
            con.execute(
                "UPDATE videos SET ai_review_count = ai_review_count + 1, updated_at = ? WHERE id = ?",
                (db._now(), video_id),
            )
            row = con.execute(
                "SELECT ai_review_count, script, tts_text, visual_style, "
                "resolved_visual_style, resolved_renderer FROM videos WHERE id = ?", (video_id,)
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
            # A Cartoon 3D video (chosen, or what "auto" settled on) is judged
            # against its own look: ink, blur and grading are the style.
            is_cartoon_3d = raw_style == "cartoon_3d" or (
                (row["resolved_renderer"] if row else "") or "") == "cartoon_3d"

        over_cap = new_count > max_review_loops

        # The scene-config the render was made from: the job's own copy (the
        # renderer staged it from the bundle the gateway built from this file).
        scene_config_path = tjobs.job_file(JOBS_DIR, video_id, tjobs.SCENE_CONFIG)
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
                                                line_art=has_line_art,
                                                cartoon_3d=is_cartoon_3d)
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
