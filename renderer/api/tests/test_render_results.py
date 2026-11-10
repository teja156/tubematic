"""The server-side render rules, render_results.py: the AI-review tail of an
uploaded render, the failure tail and its retry cap, a GPU-only video failing
when its GPU went away, re-queueing an interrupted render, and the settings
the rules read. These moved here from render_agent.py when renderers stopped
reading the database; the behaviour and the comment texts are the same.

Run from renderer/api/: pytest tests/test_render_results.py
"""
import json
import os
import sqlite3
import unittest.mock as mock

import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import pipeline as pipeline_module
import render_results

OUT = "/output_videos/proj-1/vid-1.mp4"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    p = str(tmp_path / "test.db")
    pipeline_module._init_db(p)
    monkeypatch.setattr(render_results, "DB_PATH", p)
    monkeypatch.setattr(render_results, "JOBS_DIR", tmp_path / "jobs")
    return p


def _seed_video(db_path, video_id="vid-1", status="RENDERING", render_fail_count=0, script="",
                tts_text="", video_path=OUT, renderer_id="", lease="", uploaded="2026-01-01T00:00:05Z", claim=""):
    con = sqlite3.connect(db_path)
    con.execute(
        """INSERT INTO videos
           (id, project_id, topic, strategy, producibility_score, status, render_fail_count,
            script, tts_text, video_path, renderer_id, render_lease_until, render_uploaded_at,
            render_claim_id, render_started_at, created_at, updated_at)
           VALUES (?, 'proj-1', 'DNS resolution', 'curriculum', 8, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                   '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z', '2026-01-01T00:00:00Z')""",
        (video_id, status, render_fail_count, script, tts_text, video_path, renderer_id, lease, uploaded, claim))
    con.commit()
    con.close()


def _read_video(db_path, video_id="vid-1"):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    row = con.execute("SELECT * FROM videos WHERE id = ?", (video_id,)).fetchone()
    con.close()
    return dict(row) if row else None


def _read_comments(db_path, video_id="vid-1"):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT * FROM comments WHERE video_id = ? ORDER BY id", (video_id,)).fetchall()
    con.close()
    return [dict(r) for r in rows]


def _row(db_path, key, value):
    con = sqlite3.connect(db_path)
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    con.commit()
    con.close()


def _scene_config(tmp_path, video_id="vid-1"):
    job = tmp_path / "jobs" / video_id
    job.mkdir(parents=True, exist_ok=True)
    (job / "scene-config.json").write_text('{"scenes": []}')


@pytest.fixture
def review_on(db_path, tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path)
    _scene_config(tmp_path)


def _review(**kw):
    out = {"overall": "fine", "must_fix": [], "suggestions": [], "feedback": "fine"}
    out.update(kw)
    return mock.patch.object(render_results.ai_review, "run_ai_review", return_value=out)


# ── finish_render: the AI-review tail ─────────────────────────────────────────

def test_review_disabled_sets_video_ready(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "false")
    _seed_video(db_path)
    render_results.finish_render("vid-1")
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_no_gemini_key_sets_video_ready(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _seed_video(db_path)
    render_results.finish_render("vid-1")
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_clean_review_sets_video_ready_and_reviews_the_uploaded_output(db_path, review_on):
    with _review(overall="Looks great, no issues found.", feedback="Looks great, no issues found.") as run:
        render_results.finish_render("vid-1")
    # the output path comes from the row the gateway wrote at upload
    assert run.call_args.args[0] == OUT
    video = _read_video(db_path)
    assert video["status"] == "VIDEO_READY"
    assert video["gemini_feedback"] == "Looks great, no issues found."
    assert any("AI review 1 of 1 — clean" in c["content"] and "Looks great, no issues found." in c["content"]
               for c in _read_comments(db_path))


def test_the_review_reads_the_scene_config_from_the_job_dir(db_path, review_on, tmp_path):
    (tmp_path / "jobs" / "vid-1" / "scene-config.json").write_text('{"scenes": [{"type": "x"}]}')
    with _review() as run:
        render_results.finish_render("vid-1")
    assert run.call_args.args[1] == {"scenes": [{"type": "x"}]}


def test_the_pronunciation_reference_reaches_the_review(db_path, tmp_path, monkeypatch):
    """VQA-6: the review can only check pronunciation if it is handed the
    authored wording and the exact text ElevenLabs was given."""
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path, script="Vhagar flew.", tts_text="Vah-gar flew.")
    _scene_config(tmp_path)
    with _review() as run:
        render_results.finish_render("vid-1")
    assert run.call_args.kwargs["script_text"] == "Vhagar flew."
    assert run.call_args.kwargs["tts_text"] == "Vah-gar flew."


def test_an_unvoiced_reference_passes_empty_strings(db_path, review_on):
    with _review() as run:
        render_results.finish_render("vid-1")
    assert run.call_args.kwargs["script_text"] == ""
    assert run.call_args.kwargs["tts_text"] == ""
    assert _read_video(db_path)["status"] == "VIDEO_READY"


def test_must_fix_sets_revision_requested(db_path, review_on):
    feedback = ("**Overall:** otherwise clean\n\n**Must fix (1):**\n"
                "- **text_offscreen** @ 0:07 — scene `StepFlowDiagram`\n  caption clipped\n"
                "  Suggested fix: wrap the line\n\n**Suggestions (0):**\nNo improvement suggestions.")
    with _review(overall="otherwise clean", feedback=feedback,
                 must_fix=[{"type": "text_offscreen", "timestamp": "0:07", "scene": "StepFlowDiagram",
                            "description": "caption clipped", "suggestedFix": "wrap the line"}]):
        render_results.finish_render("vid-1")
    video = _read_video(db_path)
    assert video["status"] == "REVISION_REQUESTED"
    assert video["gemini_feedback"] == feedback
    assert any("AI review 1 of 1 found 1 must-fix, 0 suggestions" in c["content"]
               and "wrap the line" in c["content"] for c in _read_comments(db_path))


def test_suggestions_only_sets_revision_requested(db_path, review_on):
    """TMDEV-58: zero must-fix but non-empty suggestions still loops back."""
    with _review(suggestions=[{"area": "video", "timestamp": "0:30", "scene": "S",
                               "description": "hold longer", "suggestedFix": "extend"}]):
        render_results.finish_render("vid-1")
    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"
    assert any("found 0 must-fix, 1 suggestions" in c["content"] for c in _read_comments(db_path))


def test_the_last_round_at_the_cap_still_routes_on_findings(db_path, review_on, monkeypatch):
    """Only new_count > cap forces acceptance: the `>` vs `>=` boundary."""
    monkeypatch.setenv("AI_REVIEW_MAX_LOOPS", "2")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET ai_review_count = 1 WHERE id = 'vid-1'")
    con.commit()
    con.close()
    with _review(must_fix=[{"type": "sync_drift"}], feedback="still one issue"):
        render_results.finish_render("vid-1")
    video = _read_video(db_path)
    assert video["ai_review_count"] == 2
    assert video["status"] == "REVISION_REQUESTED"


def test_over_the_cap_the_review_still_runs_and_forces_video_ready(db_path, review_on, monkeypatch):
    monkeypatch.setenv("AI_REVIEW_MAX_LOOPS", "2")
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET ai_review_count = 2 WHERE id = 'vid-1'")
    con.commit()
    con.close()
    fresh = "**Overall:** still has an issue"
    with _review(must_fix=[{"type": "audio_drop"}], feedback=fresh) as run:
        render_results.finish_render("vid-1")
    run.assert_called_once()
    video = _read_video(db_path)
    assert video["status"] == "VIDEO_READY"
    assert video["gemini_feedback"] == fresh
    assert any("Max AI reviews (2) reached" in c["content"] for c in _read_comments(db_path))


def test_a_cap_of_one_still_allows_one_revision_round(db_path, review_on, monkeypatch):
    monkeypatch.setenv("AI_REVIEW_MAX_LOOPS", "1")
    with _review(must_fix=[{"type": "sync_drift"}], feedback="one issue"):
        render_results.finish_render("vid-1")
    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"


def test_a_gemini_error_fails_open_to_video_ready(db_path, review_on):
    with _review(overall="", feedback="AI review did not run: Gemini upload failed: timeout",
                 error="Gemini upload failed: timeout"):
        render_results.finish_render("vid-1")
    video = _read_video(db_path)
    assert video["status"] == "VIDEO_READY"
    assert video["gemini_feedback"] == "AI review did not run: Gemini upload failed: timeout"
    assert any("AI review failed" in c["content"] for c in _read_comments(db_path))


def test_a_missing_scene_config_sets_video_ready(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path)
    render_results.finish_render("vid-1")
    assert _read_video(db_path)["status"] == "VIDEO_READY"
    assert any("scene-config.json not found" in c["content"] for c in _read_comments(db_path))


def test_an_unexpected_exception_sets_revision_requested(db_path, review_on):
    with mock.patch.object(render_results.ai_review, "run_ai_review", side_effect=Exception("disk full")):
        render_results.finish_render("vid-1")
    assert _read_video(db_path)["status"] == "REVISION_REQUESTED"
    assert any("Unexpected error in render tail" in c["content"] for c in _read_comments(db_path))


def test_model_and_fps_come_from_settings(db_path, review_on):
    _row(db_path, "ai_review_model", "gemini-3.6-flash")
    _row(db_path, "ai_review_fps", "20")
    with _review() as run:
        render_results.finish_render("vid-1")
    assert run.call_args.kwargs["model"] == "gemini-3.6-flash"
    assert run.call_args.kwargs["fps"] == "20"


def test_review_defaults_when_unset(db_path, review_on, monkeypatch):
    monkeypatch.delenv("AI_REVIEW_MODEL", raising=False)
    monkeypatch.delenv("AI_REVIEW_FPS", raising=False)
    with _review() as run:
        render_results.finish_render("vid-1")
    assert run.call_args.kwargs["model"] == "gemini-2.5-flash"
    assert run.call_args.kwargs["fps"] == "10"


def test_the_review_is_told_the_videos_register(db_path, tmp_path, monkeypatch):
    monkeypatch.setenv("GEMINI_REVIEW_ENABLED", "true")
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    _seed_video(db_path)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET visual_style = 'auto', resolved_renderer = 'cartoon_3d' WHERE id = 'vid-1'")
    con.commit()
    con.close()
    _scene_config(tmp_path)
    with _review() as run:
        render_results.finish_render("vid-1")
    assert run.call_args.kwargs["cartoon_3d"] is True


# ── Feedback storage vs comment truncation ────────────────────────────────────

def _long_review(n_chars: int = 12000) -> str:
    body = "\n".join(f"- **animation_defect** @ 0:{i:02d} — a real blocking defect number {i}" for i in range(400))
    return ("**Overall:** many problems.\n\n**Must fix (400):**\n" + body)[:n_chars]


def test_gemini_feedback_is_stored_in_full(db_path, review_on):
    feedback = _long_review()
    assert len(feedback) > 8000
    with _review(feedback=feedback):
        render_results.finish_render("vid-1")
    assert _read_video(db_path)["gemini_feedback"] == feedback


def test_a_long_review_comment_is_truncated_and_says_so(db_path, review_on):
    with _review(feedback=_long_review()):
        render_results.finish_render("vid-1")
    body = "\n".join(c["content"] for c in _read_comments(db_path))
    assert "gemini_feedback" in body and "truncated" in body
    for c in _read_comments(db_path):
        assert len(c["content"]) <= render_results._COMMENT_MAX_CHARS


def test_a_short_review_comment_is_untouched(db_path, review_on):
    with _review(feedback="**Overall:** fine.\n\nNo blocking errors."):
        render_results.finish_render("vid-1")
    assert "truncated" not in "\n".join(c["content"] for c in _read_comments(db_path))


def test_truncate_comment_helper_boundaries():
    assert render_results._truncate_comment("") == ""
    exact = "x" * render_results._COMMENT_MAX_CHARS
    assert render_results._truncate_comment(exact) == exact
    over = render_results._truncate_comment("y" * (render_results._COMMENT_MAX_CHARS + 1))
    assert len(over) <= render_results._COMMENT_MAX_CHARS
    assert over.endswith("for the complete review.")


def test_an_error_comment_keeps_the_routing_clause_when_the_error_is_long(db_path, review_on):
    with _review(overall="", feedback="AI review did not run: boom", error="Gemini review failed: " + "u" * 5000):
        render_results.finish_render("vid-1")
    body = "\n".join(c["content"] for c in _read_comments(db_path))
    assert "advancing to VIDEO_READY" in body
    assert _read_video(db_path)["status"] == "VIDEO_READY"
    for c in _read_comments(db_path):
        assert len(c["content"]) <= render_results._COMMENT_MAX_CHARS


# ── Usage recording ───────────────────────────────────────────────────────────

def _usage_rows(db_path):
    con = sqlite3.connect(db_path)
    con.row_factory = sqlite3.Row
    rows = con.execute("SELECT e.*, l.video_id FROM usage_events e "
                       "LEFT JOIN usage_event_videos l ON l.event_id = e.id").fetchall()
    con.close()
    return rows


def test_each_review_is_recorded_against_the_video(db_path, review_on):
    usage = {"model": "gemini-2.5-flash", "fps": 10,
             "usageMetadata": {"promptTokenCount": 66000, "candidatesTokenCount": 300}}
    with _review(feedback="ok", usage=usage):
        render_results.finish_render("vid-1")
    [row] = _usage_rows(db_path)
    assert (row["service"], row["model"], row["operation"], row["video_id"]) == \
        ("gemini", "gemini-2.5-flash", "ai_review", "vid-1")
    assert json.loads(row["units"]) == {"input": 66000, "output": 300}


def test_a_review_without_usage_records_nothing(db_path, review_on):
    with _review(feedback="AI review did not run: x", error="x"):
        render_results.finish_render("vid-1")
    assert _usage_rows(db_path) == []


# ── handle_render_failure and the retry cap ───────────────────────────────────

def test_a_failure_below_the_cap_sets_revision_requested(db_path):
    _seed_video(db_path, render_fail_count=0)
    render_results.handle_render_failure("vid-1", "Chromium crashed")
    video = _read_video(db_path)
    assert video["status"] == "REVISION_REQUESTED" and video["render_fail_count"] == 1
    assert _read_comments(db_path)[-1]["content"] == "Render failed: Chromium crashed"


def test_a_failure_past_the_cap_sets_failed(db_path):
    _seed_video(db_path, render_fail_count=1)
    render_results.handle_render_failure("vid-1", "Chromium crashed")
    video = _read_video(db_path)
    assert video["status"] == "FAILED" and video["render_fail_count"] == 2
    assert "giving up" in _read_comments(db_path)[-1]["content"].lower()


def test_a_raised_retry_cap_is_read(db_path):
    _row(db_path, "max_render_retries", "3")
    _seed_video(db_path, render_fail_count=2)
    render_results.handle_render_failure("vid-1", "Chromium crashed")
    video = _read_video(db_path)
    assert video["status"] == "REVISION_REQUESTED" and video["render_fail_count"] == 3


def test_the_retry_status_override_requeues(db_path):
    _seed_video(db_path)
    render_results.handle_render_failure("vid-1", "timed out", retry_status="RENDER_QUEUED")
    assert _read_video(db_path)["status"] == "RENDER_QUEUED"


def test_the_review_loop_cap_and_the_retry_cap_are_independent(db_path, monkeypatch):
    monkeypatch.delenv("AI_REVIEW_MAX_LOOPS", raising=False)
    monkeypatch.delenv("MAX_RENDER_RETRIES", raising=False)
    assert render_results.max_ai_review_loops() == 1 and render_results.max_render_retries() == 1
    _row(db_path, "ai_review_max_loops", "2")
    assert render_results.max_ai_review_loops() == 2
    assert render_results.max_render_retries() == 1


def test_the_render_settings_and_their_defaults(db_path, monkeypatch):
    for var in ("RENDER_TIMEOUT_SECS", "RENDER_STALL_TIMEOUT_SECS", "WATERMARK_ENABLED"):
        monkeypatch.delenv(var, raising=False)
    assert render_results.render_timeout_secs() == 10800
    assert render_results.render_stall_timeout_secs() == 600
    assert render_results.watermark_enabled() is True
    _row(db_path, "render_timeout_secs", "999")
    _row(db_path, "render_stall_timeout_secs", "77")
    _row(db_path, "watermark_enabled", "false")
    assert render_results.render_timeout_secs() == 999
    assert render_results.render_stall_timeout_secs() == 77
    assert render_results.watermark_enabled() is False


# ── A GPU-only video whose GPU went away ──────────────────────────────────────

def _builtin_probe(db_path, probe, verified):
    con = sqlite3.connect(db_path)
    con.execute("UPDATE renderers SET gpu_probe = ?, gpu_verified = ? WHERE id = 'builtin'",
                (json.dumps(probe), 1 if verified else 0))
    con.commit()
    con.close()


def test_fail_without_gpu_names_the_renderers_gpu_state(db_path):
    _seed_video(db_path)
    _builtin_probe(db_path, {"configured": True, "ok": False,
                             "error": "Chromium is rendering on another device: SwiftShader"}, False)
    render_results.fail_without_gpu("vid-1", cartoon=True)
    video = _read_video(db_path)
    assert video["status"] == "FAILED" and video["render_fail_count"] == 0
    [comment] = [c["content"] for c in _read_comments(db_path)]
    assert comment.startswith("Not rendered, moved to FAILED: this video is Cartoon 3D, which renders on the GPU only")
    assert "Built-in renderer" in comment and "SwiftShader" in comment
    assert "Test GPU" in comment and "--step gpu" in comment


def test_fail_without_gpu_after_a_render_carries_its_error(db_path):
    _seed_video(db_path)
    render_results.fail_without_gpu("vid-1", cartoon=False, render_error="WebGL context lost")
    comment = _read_comments(db_path)[-1]["content"]
    assert comment.startswith("Render failed, moved to FAILED: this video has a mascot")
    assert comment.endswith("The render's error: WebGL context lost")


@pytest.mark.parametrize("needs_gpu, on_gpu, gpu_ok, expected", [
    (True, True, False, "gpu"),       # the re-test found the GPU gone: FAILED, no retry
    (True, True, True, "own"),        # the GPU still works: the video's own failure
    (True, True, None, "own"),        # no answer: never failed on no evidence
    (True, False, False, "own"),      # did not run on the GPU
    (False, True, False, "own"),      # an ordinary video retries on the CPU
])
def test_after_render_failure_routes_on_the_renderers_gpu_answer(db_path, needs_gpu, on_gpu, gpu_ok, expected):
    _seed_video(db_path)
    render_results.after_render_failure("vid-1", "Error: WebGL context lost", "REVISION_REQUESTED",
                                        on_gpu, needs_gpu, False, gpu_ok)
    video = _read_video(db_path)
    comment = _read_comments(db_path)[-1]["content"]
    if expected == "gpu":
        assert video["status"] == "FAILED" and video["render_fail_count"] == 0
        assert comment.startswith("Render failed, moved to FAILED") and "GPU only" in comment
    else:
        assert video["status"] == "REVISION_REQUESTED" and video["render_fail_count"] == 1
        assert comment == "Render failed: Error: WebGL context lost"


# ── the claim a result belongs to ─────────────────────────────────────────────
#
# The gateway routes a failure result with claim=(renderer_id, claim_id). A
# lease can run out between the gateway's check and the routing, and the video
# be claimed again (by the same renderer, under a new claim id): the stale
# result must then change nothing at all.

def _claimed_video(db_path, **kw):
    _seed_video(db_path, uploaded="", renderer_id="r_a", lease="2026-01-01T00:05:00Z", claim="c-new", **kw)


@pytest.mark.parametrize("claim", [("r_a", "c-old"), ("r_b", "c-new")])
def test_a_stale_failure_result_changes_nothing(db_path, claim):
    _claimed_video(db_path)
    assert render_results.handle_render_failure("vid-1", "late crash", claim=claim) is False
    assert render_results.after_render_failure("vid-1", "late", "RENDER_QUEUED", True, True, True, False,
                                               claim=claim) is False
    assert render_results.fail_without_gpu("vid-1", cartoon=True, render_error="x", claim=claim) is False
    video = _read_video(db_path)
    assert (video["status"], video["render_fail_count"], video["renderer_id"], video["render_claim_id"]) == \
        ("RENDERING", 0, "r_a", "c-new")
    assert _read_comments(db_path) == []


def test_the_current_claims_failure_moves_the_video_and_releases_it(db_path):
    _claimed_video(db_path)
    assert render_results.handle_render_failure("vid-1", "crash", retry_status="RENDER_QUEUED",
                                                claim=("r_a", "c-new")) is True
    video = _read_video(db_path)
    assert (video["status"], video["render_fail_count"]) == ("RENDER_QUEUED", 1)
    assert (video["renderer_id"], video["render_lease_until"], video["render_claim_id"]) == ("", "", "")
    assert [c["content"] for c in _read_comments(db_path)] == ["Render failed: crash"]


def test_the_current_claims_gpu_failure_moves_the_video_and_releases_it(db_path):
    _claimed_video(db_path)
    assert render_results.fail_without_gpu("vid-1", cartoon=True, render_error="gone",
                                           claim=("r_a", "c-new")) is True
    video = _read_video(db_path)
    assert (video["status"], video["render_fail_count"], video["render_claim_id"]) == ("FAILED", 0, "")
    assert len(_read_comments(db_path)) == 1


def test_a_failure_for_a_video_no_longer_rendering_changes_nothing(db_path):
    """Moved by a human while its render ended: not counted, not commented."""
    _seed_video(db_path, status="REVISION_REQUESTED")
    assert render_results.handle_render_failure("vid-1", "crash") is False
    assert render_results.fail_without_gpu("vid-1", cartoon=False) is False
    assert _read_video(db_path)["render_fail_count"] == 0 and _read_comments(db_path) == []


# ── A page timeout inside the browser: retried once, then the agent's ─────────
# The three errors below are real renders' errors, from an install whose host
# was out of memory: the scenes were fine, and the agent was sent to rework them.

INITIAL = ('Error: Timeout (30000ms) exceeded rendering the component initially. . You can increase the timeout '
           'using the "timeoutInMilliseconds" / "--timeout" option of the function or command you used to '
           'trigger this render.\n    at /app/remotion/node_modules/@remotion/renderer/dist/seek-to-frame.js:86:28')
EVALUATE = ('Tried to get delayRender() handles for timeout, but could not do so because of Error: Timed out '
            'evaluating page function "() => {\n return Object.keys(window.remotion_delayRenderTimeouts)')


@pytest.mark.parametrize("error", [INITIAL, EVALUATE, "frames 0-449: " + EVALUATE])
def test_remotions_page_timeouts_are_recognised(error):
    assert render_results.is_page_timeout(error)


@pytest.mark.parametrize("error", ["", "Error: WebGL context lost", "SyntaxError: Unexpected token",
                                   "Render timed out after 10800s", "Error: ENOSPC: no space left on device"])
def test_other_failures_are_not_page_timeouts(error):
    assert not render_results.is_page_timeout(error)


def _fail(error, claim=("r_a", "c-new")):
    return render_results.after_render_failure("vid-1", error, "REVISION_REQUESTED", False, False, False, None,
                                               claim=claim)


def test_the_first_page_timeout_is_requeued_unchanged_and_uncounted(db_path):
    _claimed_video(db_path)
    assert _fail(INITIAL) is True
    video = _read_video(db_path)
    assert (video["status"], video["render_fail_count"]) == ("RENDER_QUEUED", 0)
    assert (video["renderer_id"], video["render_lease_until"], video["render_claim_id"]) == ("", "", "")
    [comment] = _read_comments(db_path)
    assert comment["author"] == "agent"
    assert comment["content"].startswith(render_results.PAGE_TIMEOUT_RETRY_PREFIX)
    assert "30000ms" in comment["content"]


def test_the_second_page_timeout_goes_to_the_agent_and_counts(db_path):
    """A scene that really hangs must still reach the agent: with the default
    cap of 1, a counted first retry would send this one to FAILED."""
    _claimed_video(db_path)
    _fail(INITIAL)
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET status = 'RENDERING', renderer_id = 'r_a', render_claim_id = 'c-2' "
                "WHERE id = 'vid-1'")
    con.commit()
    con.close()
    assert _fail(EVALUATE, claim=("r_a", "c-2")) is True
    video = _read_video(db_path)
    assert (video["status"], video["render_fail_count"]) == ("REVISION_REQUESTED", 1)
    assert _read_comments(db_path)[-1]["content"].startswith(
        f"Render failed: {render_results.PAGE_TIMEOUT_AGAIN} Tried to get delayRender()")


def test_the_retry_cap_still_applies_to_the_second_page_timeout(db_path):
    """The uncounted retry does not lift the cap: a video that already used
    its retry on something else (a stall, a renderer restart) goes to FAILED
    on its second page timeout, as any failure past the cap does."""
    _claimed_video(db_path, render_fail_count=1)
    _fail(INITIAL)
    assert _read_video(db_path)["status"] == "RENDER_QUEUED"
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET status = 'RENDERING', renderer_id = 'r_a', render_claim_id = 'c-2' "
                "WHERE id = 'vid-1'")
    con.commit()
    con.close()
    assert _fail(EVALUATE, claim=("r_a", "c-2")) is True
    video = _read_video(db_path)
    assert (video["status"], video["render_fail_count"]) == ("FAILED", 2)


def test_a_stale_page_timeout_result_changes_nothing(db_path):
    _claimed_video(db_path)
    assert _fail(INITIAL, claim=("r_a", "c-old")) is False
    video = _read_video(db_path)
    assert (video["status"], video["render_claim_id"]) == ("RENDERING", "c-new")
    assert _read_comments(db_path) == []


def test_any_other_failure_still_goes_to_the_agent(db_path):
    _claimed_video(db_path)
    assert _fail("SyntaxError: Unexpected token") is True
    video = _read_video(db_path)
    assert (video["status"], video["render_fail_count"]) == ("REVISION_REQUESTED", 1)


def test_a_gpu_that_failed_its_retest_still_fails_the_video_on_a_page_timeout(db_path):
    _claimed_video(db_path)
    assert render_results.after_render_failure("vid-1", INITIAL, "REVISION_REQUESTED", True, True, True, False,
                                               claim=("r_a", "c-new")) is True
    assert _read_video(db_path)["status"] == "FAILED"


def test_a_stall_or_timeout_outcome_keeps_its_own_path(db_path):
    """Requeued stalls and timeouts are already environmental and counted;
    the page-timeout rule applies to a failed render only."""
    _claimed_video(db_path)
    assert render_results.after_render_failure("vid-1", INITIAL, "RENDER_QUEUED", False, False, False, None,
                                               claim=("r_a", "c-new")) is True
    video = _read_video(db_path)
    assert (video["status"], video["render_fail_count"]) == ("RENDER_QUEUED", 1)
    assert _read_comments(db_path)[0]["content"].startswith("Render failed:")


# ── requeue_interrupted ───────────────────────────────────────────────────────

def test_an_interrupted_render_is_requeued_with_a_retry_counted(db_path):
    _seed_video(db_path, uploaded="", renderer_id="r_a", lease="2026-01-01T00:05:00Z", claim="c1")
    assert render_results.requeue_interrupted("vid-1", render_results.RESTART_COMMENT) is True
    video = _read_video(db_path)
    assert video["status"] == "RENDER_QUEUED" and video["render_fail_count"] == 1
    assert (video["renderer_id"], video["render_lease_until"], video["render_started_at"],
            video["render_uploaded_at"], video["render_claim_id"]) == ("", "", "", "", "")
    assert _read_comments(db_path)[-1]["content"] == \
        "Render interrupted by renderer restart — automatically re-queued."


def test_an_interrupted_render_past_the_cap_fails_with_the_old_wording(db_path):
    _seed_video(db_path, uploaded="", render_fail_count=1)
    render_results.requeue_interrupted("vid-1", render_results.RESTART_COMMENT)
    video = _read_video(db_path)
    assert video["status"] == "FAILED" and video["render_fail_count"] == 2
    assert _read_comments(db_path)[-1]["content"] == \
        "Render interrupted by renderer restart 2 times (limit 1) — giving up."


def test_an_uploaded_render_is_never_requeued(db_path):
    """Its render is finished; the review thread owns it."""
    _seed_video(db_path, uploaded="2026-01-01T00:00:05Z")
    assert render_results.requeue_interrupted("vid-1", render_results.RESTART_COMMENT) is False
    assert _read_video(db_path)["status"] == "RENDERING"
    assert _read_comments(db_path) == []


def test_requeue_is_guarded_on_the_holder_and_the_lease(db_path):
    _seed_video(db_path, uploaded="", renderer_id="r_a", lease="2026-01-01T00:05:00Z")
    # another renderer's re-queue does nothing
    assert render_results.requeue_interrupted("vid-1", "x — automatically re-queued.", renderer_id="r_b") is False
    # a lease extended past the sweep's clock wins
    assert render_results.requeue_interrupted("vid-1", "x — automatically re-queued.", renderer_id="r_a",
                                              lease_expired_before="2026-01-01T00:04:00Z") is False
    assert _read_video(db_path)["status"] == "RENDERING"
    assert render_results.requeue_interrupted("vid-1", "x — automatically re-queued.", renderer_id="r_a",
                                              lease_expired_before="2026-01-01T00:06:00Z") is True


def test_a_video_not_rendering_is_left_alone(db_path):
    _seed_video(db_path, status="VOICING", uploaded="")
    assert render_results.requeue_interrupted("vid-1", render_results.RESTART_COMMENT) is False
    assert _read_video(db_path)["status"] == "VOICING"


# ── _setting precedence (TMDEV-73) ────────────────────────────────────────────

def test_setting_prefers_a_populated_row_over_env(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    _row(db_path, "gemini_api_key", "from-db")
    assert render_results._setting("gemini_api_key", "") == "from-db"


def test_setting_falls_back_to_env_when_no_row_exists(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    assert render_results._setting("gemini_api_key", "") == "from-env"


def test_a_blank_row_falls_through_to_env(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    _row(db_path, "gemini_api_key", "")
    assert render_results._setting("gemini_api_key", "") == "from-env"


def test_a_blank_row_and_no_env_yields_the_default(db_path, monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    _row(db_path, "gemini_api_key", "")
    assert render_results._setting("gemini_api_key", "fallback") == "fallback"


def test_a_blank_row_does_not_break_the_int_settings(db_path, monkeypatch):
    monkeypatch.delenv("MAX_RENDER_RETRIES", raising=False)
    _row(db_path, "max_render_retries", "")
    assert render_results.max_render_retries() == 1


def test_the_render_rules_match_the_other_key_readers(db_path, monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "from-env")
    _row(db_path, "gemini_api_key", "")
    assert render_results._setting("gemini_api_key", "") == \
        pipeline_module._secret({"gemini_api_key": ""}, "gemini_api_key", "GEMINI_API_KEY")


# ── The Cartoon 3D scene-config check ─────────────────────────────────────────

def test_a_cartoon_scene_config_is_recognised(tmp_path, db_path):
    job = tmp_path / "jobs" / "vid-1"
    job.mkdir(parents=True)
    (job / "scene-config.json").write_text(json.dumps(
        {"scenes": [{"type": "generated", "src": "vid-1/C", "props": {"cartoon3d": {"beats": []}}}]}))
    assert render_results.video_scene_is_cartoon3d("vid-1") is True
    (job / "scene-config.json").write_text('{"scenes": [{"type": "generated", "src": "vid-1/C"}]}')
    assert render_results.video_scene_is_cartoon3d("vid-1") is False
    assert render_results.video_scene_is_cartoon3d("../x") is False


def test_the_scene_config_marker_is_the_cartoon3d_props(tmp_path):
    """Moved from the renderer with the check itself: only a generated scene
    whose props carry a `cartoon3d` object is a Cartoon 3D world."""
    p = tmp_path / "scene-config.json"
    p.write_text(json.dumps({"scenes": [{"src": "v/CartoonShort", "props": {"cartoon3d": {"beats": []}}}]}))
    assert render_results.scene_config_is_cartoon3d(p)
    p.write_text(json.dumps({"scenes": [{"src": "Cartoon3D", "source": "installed", "props": {"world": {}}}]}))
    assert not render_results.scene_config_is_cartoon3d(p)          # the data-driven marker of 2.0 is not one any more
    p.write_text(json.dumps({"scenes": [{"src": "v/intro", "props": {"cartoon3d": "yes"}}]}))
    assert not render_results.scene_config_is_cartoon3d(p)
    p.write_text("not json")
    assert not render_results.scene_config_is_cartoon3d(p)


def test_the_failure_count_persists_across_attempts(db_path):
    """render_fail_count is never reset between attempts, mirroring ai_review_count."""
    _seed_video(db_path, render_fail_count=0)
    render_results.handle_render_failure("vid-1", "crash 1")
    assert _read_video(db_path)["render_fail_count"] == 1
    con = sqlite3.connect(db_path)
    con.execute("UPDATE videos SET status = 'RENDERING' WHERE id = 'vid-1'")
    con.commit()
    con.close()
    render_results.handle_render_failure("vid-1", "crash 2")
    assert _read_video(db_path)["render_fail_count"] == 2
