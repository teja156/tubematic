"""Wire-level tests for ai_review.py (TMDEV-46, reshaped for TMDEV-58).

The existing AI-review tests in test_pipeline.py mock httpx.Client wholesale
(client_instance.post.side_effect = [...]), which accepts any URL/headers/
params — none of them would have caught the original bug (uploading to the
wrong endpoint entirely) or the API-key-in-query-param leak. These tests use
httpx.MockTransport so real httpx.Request objects reach the assertions:
method, path, headers, and query string are all genuinely exercised.

Run from renderer/api/: pytest tests/test_ai_review.py
"""
import json
import os

import httpx
import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import ai_review

# Captured before any test monkeypatches httpx.Client -- the mock factory
# below must build real Client instances (with a MockTransport swapped in),
# not recurse into itself once httpx.Client has been reassigned.
_RealHttpxClient = httpx.Client

UPLOAD_START_RESPONSE_HEADERS = {
    "x-goog-upload-url": "https://generativelanguage.googleapis.com/upload/v1beta/files/session-abc",
}


def _json_response(request, status_code=200, json_body=None, headers=None):
    return httpx.Response(status_code, json=json_body or {}, headers=headers or {}, request=request)


def _make_client_factory(handler):
    """Return a callable that stands in for httpx.Client, wiring `handler`
    in as the MockTransport so no real network call is ever made."""
    def _factory(*args, **kwargs):
        kwargs.pop("timeout", None)
        return _RealHttpxClient(transport=httpx.MockTransport(handler), **kwargs)
    return _factory


def _default_handler(requests, *, generate_body, file_states=("ACTIVE",)):
    """Builds a handler that records every request it sees and returns the
    documented response for each of the four request kinds in sequence:
    POST .../upload/v1beta/files (start) -> PUT <upload_url> (bytes) ->
    GET .../files/{name} (poll, once per entry in file_states) ->
    POST .../models/{model}:generateContent.
    """
    state = {"poll_index": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path

        if request.method == "POST" and path == "/upload/v1beta/files":
            return _json_response(request, headers=UPLOAD_START_RESPONSE_HEADERS)

        if request.method == "POST" and path == "/upload/v1beta/files/session-abc":
            return _json_response(request, json_body={
                "file": {"uri": "https://generativelanguage.googleapis.com/v1beta/files/abc123",
                          "name": "files/abc123"},
            })

        if request.method == "GET" and path == "/v1beta/files/abc123":
            idx = min(state["poll_index"], len(file_states) - 1)
            current_state = file_states[idx]
            state["poll_index"] += 1
            return _json_response(request, json_body={"state": current_state})

        if request.method == "POST" and path.startswith("/v1beta/models/") and path.endswith(":generateContent"):
            return _json_response(request, json_body=generate_body)

        raise AssertionError(f"unexpected request: {request.method} {request.url}")

    return handler


@pytest.fixture
def video_file(tmp_path):
    p = tmp_path / "video.mp4"
    p.write_bytes(b"fake-video-bytes")
    return p


_CLEAN_BODY = {
    "candidates": [{"content": {"parts": [
        {"text": '{"overall": "Looks good.", "mustFix": [], "suggestions": []}'}
    ]}}]
}


def test_upload_uses_resumable_start_endpoint(monkeypatch, video_file):
    """Regression test for the reported 400: the start request must hit the
    /upload/v1beta/files path (not /v1beta/files) with the resumable protocol
    headers Google's Files API requires."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body=_CLEAN_BODY)
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    assert "error" not in result
    start_req = requests[0]
    assert start_req.method == "POST"
    assert start_req.url.path == "/upload/v1beta/files"
    assert start_req.headers["x-goog-upload-protocol"] == "resumable"
    assert start_req.headers["x-goog-upload-command"] == "start"


def test_upload_bytes_sent_to_returned_session_url(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body=_CLEAN_BODY)
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    ai_review.run_ai_review(str(video_file), {})

    upload_req = requests[1]
    assert upload_req.method == "POST"
    assert upload_req.url.path == "/upload/v1beta/files/session-abc"
    assert upload_req.headers["x-goog-upload-command"] == "upload, finalize"
    assert upload_req.content == b"fake-video-bytes"


def test_polls_until_active_not_just_once(monkeypatch, video_file):
    """A single-ACTIVE fixture would pass even against code with no polling
    loop at all -- assert on the number of GET requests to prove it loops."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(
        requests,
        generate_body=_CLEAN_BODY,
        file_states=("PROCESSING", "PROCESSING", "ACTIVE"),
    )
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))
    monkeypatch.setattr(ai_review, "_POLL_INTERVAL_SECS", 0)

    result = ai_review.run_ai_review(str(video_file), {})

    assert "error" not in result
    poll_requests = [r for r in requests if r.method == "GET"]
    assert len(poll_requests) == 3


def test_generate_content_called_after_active(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body={
        "candidates": [{"content": {"parts": [
            {"text": '{"overall": "has a sync issue", "mustFix": [{"type": "sync_drift"}], "suggestions": []}'}
        ]}}]
    })
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {"scenes": []})

    assert [d["type"] for d in result["must_fix"]] == ["sync_drift"]
    assert result["suggestions"] == []
    generate_req = requests[-1]
    assert generate_req.url.path == "/v1beta/models/gemini-2.5-flash:generateContent"


def test_no_request_carries_key_in_query_string(monkeypatch, video_file):
    """Regression test for the API-key leak: httpx error strings embed the
    request URL, so the key must never travel as a `?key=` query param on
    any of the four requests -- only as the x-goog-api-key header."""
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key")
    requests = []
    handler = _default_handler(requests, generate_body=_CLEAN_BODY)
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    ai_review.run_ai_review(str(video_file), {})

    assert len(requests) >= 4
    for req in requests:
        assert "key=" not in str(req.url)
        assert "super-secret-key" not in str(req.url)


def test_file_processing_failed_state_fails_open(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body={}, file_states=("FAILED",))
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    assert result["must_fix"] == []
    assert result["suggestions"] == []
    assert "failed" in result["error"].lower()


def test_poll_timeout_fails_open(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body={}, file_states=("PROCESSING",))
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))
    monkeypatch.setattr(ai_review, "_POLL_ATTEMPTS", 3)
    monkeypatch.setattr(ai_review, "_POLL_INTERVAL_SECS", 0)

    result = ai_review.run_ai_review(str(video_file), {})

    assert result["must_fix"] == []
    assert result["suggestions"] == []
    assert "timed out" in result["error"].lower()
    poll_requests = [r for r in requests if r.method == "GET"]
    assert len(poll_requests) == 3


def test_non_string_must_fix_type_is_coerced_not_raised(monkeypatch, video_file):
    """Gemini returning a must-fix entry missing/with a bad `type` must not
    turn fail-open into fail-closed one layer up (worker.py's persistence
    of these fields)."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body={
        "candidates": [{"content": {"parts": [
            {"text": '{"overall": "", "mustFix": [{"description": "no type key"}, '
                     '{"type": "sync_drift"}], "suggestions": []}'}
        ]}}]
    })
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    assert all(isinstance(d["type"], str) for d in result["must_fix"])
    types = [d["type"] for d in result["must_fix"]]
    assert "sync_drift" in types
    assert "unknown" in types


def test_structured_must_fix_feedback_names_scene_timestamp_and_fix(monkeypatch, video_file):
    """A well-formed structured must-fix entry must show up in `feedback`
    with its scene, timestamp and suggested fix -- bare category names
    aren't actionable feedback (TMDEV-46 follow-up, preserved under the
    TMDEV-58 reshape)."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body={
        "candidates": [{"content": {"parts": [{"text": (
            '{"overall": "otherwise clean", '
            '"mustFix": [{"type": "text_offscreen", "timestamp": "0:07", '
            '"scene": "StepFlowDiagram", "description": "caption clipped on the right edge", '
            '"suggestedFix": "shrink font size or wrap the line"}], "suggestions": []}'
        )}]}}]
    })
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    assert [d["type"] for d in result["must_fix"]] == ["text_offscreen"]
    assert "0:07" in result["feedback"]
    assert "StepFlowDiagram" in result["feedback"]
    assert "shrink font size or wrap the line" in result["feedback"]
    assert "caption clipped on the right edge" in result["feedback"]


def test_clean_pass_feedback_carries_overall(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body={
        "candidates": [{"content": {"parts": [
            {"text": '{"overall": "Looks great, captions crisp throughout.", '
                     '"mustFix": [], "suggestions": []}'}
        ]}}]
    })
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    assert result["must_fix"] == []
    assert result["suggestions"] == []
    assert "Looks great, captions crisp throughout." in result["feedback"]
    assert "No blocking errors found." in result["feedback"]
    assert "No improvement suggestions." in result["feedback"]


def test_suggestions_only_response_has_empty_must_fix(monkeypatch, video_file):
    """The headline case this ticket exists for: no mechanical defect fires,
    but the model still has real critique to offer."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body={
        "candidates": [{"content": {"parts": [{"text": (
            '{"overall": "Solid video, a couple of polish items.", "mustFix": [], '
            '"suggestions": [{"area": "video", "timestamp": "0:30", "scene": "StepFlow.tsx", '
            '"description": "hook title could hold a beat longer", '
            '"suggestedFix": "extend by 12 frames"}]}'
        )}]}}]
    })
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    assert result["must_fix"] == []
    assert len(result["suggestions"]) == 1
    assert result["suggestions"][0]["area"] == "video"
    assert "hook title could hold a beat longer" in result["feedback"]
    assert "extend by 12 frames" in result["feedback"]
    assert "No blocking errors found." in result["feedback"]


def test_feedback_section_order_is_overall_then_must_fix_then_suggestions(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body={
        "candidates": [{"content": {"parts": [{"text": (
            '{"overall": "Mixed bag.", '
            '"mustFix": [{"type": "audio_drop", "description": "silence at 1:00"}], '
            '"suggestions": [{"area": "audio", "description": "mix could be louder"}]}'
        )}]}}]
    })
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    feedback = result["feedback"]
    overall_idx = feedback.index("Mixed bag.")
    must_fix_idx = feedback.index("silence at 1:00")
    suggestions_idx = feedback.index("mix could be louder")
    assert overall_idx < must_fix_idx < suggestions_idx


def test_malformed_must_fix_and_suggestion_elements_do_not_raise(monkeypatch, video_file):
    """None, a dict missing its distinguishing key, a bare string, and a
    nested list must all be tolerated -- Gemini's response_mime_type=json
    doesn't guarantee schema adherence."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body={
        "candidates": [{"content": {"parts": [{"text": (
            '{"overall": "", '
            '"mustFix": [null, {"description": "no type key"}, [1, 2], "bare defect"], '
            '"suggestions": [null, {"description": "no area key"}, "bare suggestion text"]}'
        )}]}}]
    })
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    assert all(isinstance(d["type"], str) for d in result["must_fix"])
    assert all(isinstance(d["area"], str) for d in result["suggestions"])
    assert result["feedback"]  # non-empty

    # A bare-string must-fix entry's text belongs in `type` (matches the old
    # bare-defect-name behavior).
    assert any(d["type"] == "bare defect" for d in result["must_fix"])

    # A bare-string suggestion is free-form critique text, not an `area`
    # label -- it must land in `description`, and `area` must still default
    # sensibly, or the rendered feedback shows the suggestion text glued
    # onto the bold "area" position with no description underneath.
    bare_suggestion = next(d for d in result["suggestions"] if d["description"] == "bare suggestion text")
    assert bare_suggestion["area"] == "video"


def test_error_path_feedback_is_non_empty_and_redacted(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Bad Request for key=super-secret-key", request=request)

    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    assert result["must_fix"] == []
    assert result["suggestions"] == []
    assert result["feedback"]
    assert "super-secret-key" not in result["feedback"]


def test_key_redacted_from_upload_error_message(monkeypatch, video_file):
    """Belt-and-braces: even if an error string somehow contained the raw
    key (e.g. a signed URL echoed back by a proxy), _redact must strip it."""
    monkeypatch.setenv("GEMINI_API_KEY", "super-secret-key")

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="Bad Request for key=super-secret-key", request=request)

    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {})

    assert result["must_fix"] == []
    assert result["suggestions"] == []
    assert "super-secret-key" not in result["error"]


# ── VQA-6: pronunciation reference text ─────────────────────────────────────
#
# The prompt wording itself is prose fed to an LLM and can't be unit-tested;
# what is testable is the plumbing — that the reference actually reaches the
# generateContent payload, in the right one of the four shapes.

def _prompt_text(request: httpx.Request) -> str:
    """The text part of a generateContent request (part 0 is the video)."""
    return json.loads(request.content)["contents"][0]["parts"][1]["text"]


def _run_and_capture_prompt(monkeypatch, video_file, **kwargs) -> str:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body=_CLEAN_BODY)
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {}, **kwargs)

    assert "error" not in result
    return _prompt_text(requests[-1])


def test_mispronunciation_is_a_required_must_fix_category(monkeypatch, video_file):
    prompt = _run_and_capture_prompt(monkeypatch, video_file)
    assert "mispronunciation" in prompt


def test_both_script_forms_reach_the_prompt_when_they_differ(monkeypatch, video_file):
    prompt = _run_and_capture_prompt(
        monkeypatch, video_file, script_text="Vhagar flew.", tts_text="Vah-gar flew."
    )
    assert "Vhagar flew." in prompt
    assert "Vah-gar flew." in prompt
    assert "AS WRITTEN" in prompt and "AS SPOKEN" in prompt
    # The negative control the whole feature depends on: a deliberate respelling
    # must be presented as correct, not as something to report. VQA-8 reworded
    # this from a blanket "audio matching AS SPOKEN is correct by design" —
    # that phrasing exonerated the audio wholesale, so assert the narrower
    # claim that replaced it rather than the old wording.
    assert "never itself a defect" in prompt
    # ...and the other half of the rework: the exoneration is scoped to words
    # that actually differ, so a non-respelled name is still judged normally.
    assert "gets no benefit of the doubt" in prompt


def test_the_differ_branch_says_an_ipa_transcription_is_pronounced_not_read(monkeypatch, video_file):
    """On eleven_v3 an <ipa> tag reaches tts_text as "/.../". Without this the
    reviewer can take the slashes as text that should have been read out, and
    a working IPA term becomes a mispronunciation finding — a paid re-voice
    every round."""
    prompt = _run_and_capture_prompt(
        monkeypatch, video_file, script_text="Vhagar flew.", tts_text='"/vɑːˈɡɑːr/" flew.'
    )
    assert '"/vɑːˈɡɑːr/" flew.' in prompt
    assert "IPA" in prompt
    assert "pronounces it rather than reading it out" in prompt


def test_identical_script_forms_say_no_respelling_applies(monkeypatch, video_file):
    """An absent/empty reference section makes the model hunt for a difference
    that isn't there — say outright that there is none."""
    prompt = _run_and_capture_prompt(
        monkeypatch, video_file, script_text="Plain words.", tts_text="Plain words."
    )
    assert "no pronunciation respelling" in prompt
    assert "AS SPOKEN" not in prompt
    assert prompt.count("Plain words.") == 1


def test_prompt_names_the_reference_as_unavailable_when_neither_is_passed(monkeypatch, video_file):
    """Existing callers that pass neither (and rows voiced before tts_text was
    recorded) must still produce a usable prompt, not a blank section."""
    prompt = _run_and_capture_prompt(monkeypatch, video_file)
    assert "No script reference is available" in prompt


def test_reference_block_falls_back_to_whichever_form_is_available():
    script_only = ai_review._reference_text_block("Vhagar flew.", "")
    assert "Vhagar flew." in script_only
    assert "was not recorded" in script_only

    tts_only = ai_review._reference_text_block("", "Vah-gar flew.")
    assert "Vah-gar flew." in tts_only
    assert "correct by design" in tts_only


def test_reference_block_ignores_whitespace_only_differences():
    """Leading/trailing whitespace is not a respelling — treating it as one
    would tell the model to look for a difference it can't hear."""
    block = ai_review._reference_text_block("Plain words.", "  Plain words.\n")
    assert "AS SPOKEN" not in block
    assert "no pronunciation respelling" in block


# ── Model selection and video sampling (VQA-7) ─────────────────────────────
#
# The tokens-per-frame constants these clamp tests rest on were measured
# against the live countTokens endpoint on a real 225s render, not taken from
# the docs (which give three mutually inconsistent figures). See the comment
# on _TOKENS_PER_FRAME in ai_review.py.

def _video_part(request: httpx.Request) -> dict:
    """Part 0 of a generateContent request — the video."""
    return json.loads(request.content)["contents"][0]["parts"][0]


def _run_and_capture_request(monkeypatch, video_file, scene_config=None, **kwargs):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    requests = []
    handler = _default_handler(requests, generate_body=_CLEAN_BODY)
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), scene_config or {}, **kwargs)

    assert "error" not in result
    return requests[-1]


def test_no_fps_requested_sends_no_video_metadata(monkeypatch, video_file):
    """0/unset must reproduce the pre-VQA-7 request byte for byte. Existing
    callers that pass no fps (and test_pipeline.py's fixed-response mocks)
    depend on the request shape not changing underneath them."""
    monkeypatch.delenv("AI_REVIEW_FPS", raising=False)
    part = _video_part(_run_and_capture_request(monkeypatch, video_file))
    assert "video_metadata" not in part
    assert part["file_data"]["mime_type"] == "video/mp4"


def test_fps_is_a_sibling_of_file_data_not_nested_inside_it(monkeypatch, video_file):
    """The single most important assertion in this file: Google's own docs
    have shown video_metadata nested inside the media field, which is a real
    proto field mismatch and fails silently rather than erroring."""
    part = _video_part(_run_and_capture_request(monkeypatch, video_file, fps=10))
    assert part["video_metadata"] == {"fps": 10}
    assert "video_metadata" not in part["file_data"]


def test_fps_falls_back_to_env_when_not_passed(monkeypatch, video_file):
    monkeypatch.setenv("AI_REVIEW_FPS", "6")
    part = _video_part(_run_and_capture_request(monkeypatch, video_file))
    assert part["video_metadata"] == {"fps": 6}


def test_fps_is_capped_at_the_api_maximum(monkeypatch, video_file):
    """The documented valid range is (0, 24] — a larger value is a 400."""
    part = _video_part(_run_and_capture_request(monkeypatch, video_file, fps=90))
    assert part["video_metadata"] == {"fps": ai_review.MAX_REVIEW_FPS}


def test_model_kwarg_changes_the_request_path(monkeypatch, video_file):
    """The model id's only observable effect is the URL it is interpolated
    into, so this is the sole point at which model selection can be tested."""
    request = _run_and_capture_request(monkeypatch, video_file, model="gemini-3.6-flash")
    assert request.url.path == "/v1beta/models/gemini-3.6-flash:generateContent"


def test_model_falls_back_to_env_then_default(monkeypatch, video_file):
    monkeypatch.setenv("AI_REVIEW_MODEL", "gemini-3.5-flash")
    request = _run_and_capture_request(monkeypatch, video_file)
    assert request.url.path == "/v1beta/models/gemini-3.5-flash:generateContent"

    # GEMINI_MODEL is kept as a lower-priority fallback: it is documented in
    # docs/infrastructure.md as an override and dropping it would silently
    # retire it for existing installs.
    monkeypatch.delenv("AI_REVIEW_MODEL")
    monkeypatch.setenv("GEMINI_MODEL", "gemini-2.5-flash")
    request = _run_and_capture_request(monkeypatch, video_file)
    assert request.url.path == "/v1beta/models/gemini-2.5-flash:generateContent"


def test_prompt_states_the_actual_sampling_rate(monkeypatch, video_file):
    """Telling the model it only has 1 frame/sec when it has 10 would waste
    the whole point of raising the rate."""
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file, fps=10))
    assert "sampled at 10 frames per second" in prompt

    monkeypatch.delenv("AI_REVIEW_FPS", raising=False)
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert "sampled at 1 frames per second" in prompt


# ── _effective_fps clamp ───────────────────────────────────────────────────

_SHORT = {"totalFrames": 30 * 90, "fps": 30}       # 90s
_TYPICAL = {"totalFrames": 30 * 250, "fps": 30}    # 250s — the real worst case
_VERY_LONG = {"totalFrames": 30 * 1200, "fps": 30}  # 20 min


def test_clamp_leaves_a_typical_video_at_the_requested_rate():
    """250s at 10fps on the default model is ~666k tokens — inside budget, so
    the clamp must not fire on the ordinary case."""
    assert ai_review._effective_fps(10, _TYPICAL, "gemini-2.5-flash") == 10
    assert ai_review._effective_fps(10, _SHORT, "gemini-2.5-flash") == 10


def test_clamp_reduces_fps_for_a_video_that_would_overrun_the_window():
    got = ai_review._effective_fps(10, _VERY_LONG, "gemini-2.5-flash")
    assert 1 <= got < 10
    duration = 1200
    est = duration * got * ai_review._TOKENS_PER_FRAME["gemini-2.5-flash"] \
        + duration * ai_review._AUDIO_TOKENS_PER_SEC
    assert est <= ai_review._VIDEO_TOKEN_BUDGET


def test_clamp_is_model_aware():
    """gemini-3.x tokenises video ~3.7x more cheaply (71 vs 263 tokens/frame,
    measured), so it affords a higher rate on the same video. Using one
    constant for every model would needlessly throttle the better model."""
    long_ish = {"totalFrames": 30 * 600, "fps": 30}
    cheap = ai_review._effective_fps(20, long_ish, "gemini-3.6-flash")
    dear  = ai_review._effective_fps(20, long_ish, "gemini-2.5-flash")
    assert cheap > dear


def test_clamp_assumes_the_priciest_model_when_it_does_not_recognise_one():
    unknown = ai_review._effective_fps(20, _VERY_LONG, "some-future-model")
    known   = ai_review._effective_fps(20, _VERY_LONG, "gemini-2.5-flash")
    assert unknown == known


def test_clamp_never_drops_below_one_frame_per_second():
    """1fps is Gemini's own default; returning 0 would silently mean 'send no
    video_metadata', which is a different thing from 'sample as little as
    possible' and would hide the overrun rather than bound it."""
    absurd = {"totalFrames": 30 * 100_000, "fps": 30}
    assert ai_review._effective_fps(10, absurd, "gemini-2.5-flash") == 1


def test_clamp_passes_the_request_through_when_duration_is_unknowable():
    """A malformed or empty scene config must not silently throttle the
    review — guessing a duration would be worse than honouring the request,
    and an over-budget request only fails open."""
    for config in ({}, {"totalFrames": 0, "fps": 30}, {"totalFrames": 900, "fps": 0},
                   {"totalFrames": "many", "fps": 30}, None):
        assert ai_review._effective_fps(10, config or {}, "gemini-2.5-flash") == 10


def test_clamp_treats_junk_fps_as_unset():
    assert ai_review._effective_fps("", _TYPICAL, "gemini-2.5-flash") == 0
    assert ai_review._effective_fps(None, _TYPICAL, "gemini-2.5-flash") == 0
    assert ai_review._effective_fps("abc", _TYPICAL, "gemini-2.5-flash") == 0
    assert ai_review._effective_fps(-5, _TYPICAL, "gemini-2.5-flash") == 0
    # ...but a numeric string is a legitimate settings-table value.
    assert ai_review._effective_fps("10", _TYPICAL, "gemini-2.5-flash") == 10


# ── Prompt quality bars (VQA-7 bullet 2, VQA-8 item 2) ─────────────────────

def test_prompt_no_longer_demands_a_suggestion_on_every_review(monkeypatch, video_file):
    """The 'expect at least one suggestion on nearly every review' quota was
    manufacturing the cosmetic-invention findings this ticket exists to stop:
    under TMDEV-58 any finding routes to REVISION_REQUESTED, so a quota is a
    guaranteed revision loop."""
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert "expect to have at least one suggestion" not in prompt
    assert 'return an empty "suggestions" list' in prompt


def test_prompt_forbids_decorative_suggestions(monkeypatch, video_file):
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert "Do NOT propose decorative additions" in prompt


def test_mispronunciation_names_non_english_proper_nouns_in_scope(monkeypatch, video_file):
    """VQA-8 proposed loosening this category because it was believed to be
    missing Lanka/Rama/Ravana. A live baseline run disproved that: the
    unchanged VQA-6 wording already reports all of them, correctly grouped
    into one mustFix finding. The miss came from pre-VQA-6 code, where the
    category did not exist at all.

    So only the clarifications survive — naming the non-technical name classes
    that were never obviously in scope, and forcing enumeration. The bar
    itself is deliberately NOT lowered; see the companion test below."""
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert "Non-English, transliterated and mythological proper nouns" in prompt
    assert "Lanka, Rama, Ravana" in prompt


def test_mispronunciation_bar_is_not_lowered(monkeypatch, video_file):
    """The guard on the above. Every finding routes to REVISION_REQUESTED and
    a pronunciation fix costs a paid re-voice, so a false positive here is
    more expensive than a miss — and the category is live-proven to catch the
    class it was suspected of missing. Loosening it would be pure downside.

    These three assertions are the wording that was tried and reverted."""
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert "pronounced objectively wrong" in prompt
    assert "regional pronunciation variants are NOT defects" in prompt
    assert "You do not need certainty" not in prompt
    assert "phonology of the wrong language" not in prompt


def test_mispronunciation_still_groups_into_one_finding(monkeypatch, video_file):
    """VQA-6 deliberately compressed all mispronunciations into one finding so
    a seventh category could not crowd the other six out of the 5-entry cap.
    Loosening the category must not quietly undo that."""
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert "in ONE finding" in prompt


def test_prompt_asks_the_model_to_enumerate_proper_nouns(monkeypatch, video_file):
    """Enumeration belongs in the model's reasoning, not the emitted JSON —
    an extra output key would eat into the caps VQA-6 set deliberately."""
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert "one at a time" in prompt
    assert "pronunciationChecked" not in prompt


# ── Response budget (VQA-7 follow-up) ──────────────────────────────────────

def test_prompt_does_not_cap_must_fix_entries(monkeypatch, video_file):
    """Must-fix entries are blocking defects. Capping them meant a video with
    six real problems silently reported five, and the sixth surfaced only
    after another render + review round."""
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert "there is no limit on \"mustFix\"" in prompt
    assert "at most 5 entries under \"mustFix\"" not in prompt


def test_prompt_still_caps_suggestions_at_five(monkeypatch, video_file):
    """Suggestions stay capped — they are non-blocking, and an unbounded list
    of them is what buries the must-fix items a human actually has to act on."""
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert 'Cap "suggestions" at 5' in prompt


def test_prompt_drops_the_hard_character_limit_but_asks_for_compactness(monkeypatch, video_file):
    prompt = _prompt_text(_run_and_capture_request(monkeypatch, video_file))
    assert "under 200 characters" not in prompt
    assert "no hard character limit" in prompt
    assert "as compact as you can" in prompt


# ── Subtitles in the review prompt (TMDEV-101) ──────────────────────────────

def test_the_prompt_tells_the_reviewer_captions_are_by_design():
    """The negative control, and the reason it matters more than the positive
    one: every video is captioned now, so a reviewer that reads the captions as
    clutter or as text duplicating the narration would return a finding on
    EVERY video. Any finding routes to REVISION_REQUESTED, so that is a wedged
    pipeline, not a missed check."""
    prompt = ai_review._REVIEW_PROMPT
    assert "THAT IS BY DESIGN AND IS CORRECT" in prompt
    assert "Do not report the presence of" in prompt


def test_the_prompt_tells_the_reviewer_the_watermark_is_intentional():
    """Same shape as the captions control above, and the same cost if it goes:
    the mark is in every frame of every video, so a reviewer that reads it as
    clutter, as a safe-zone breach or as something covering the scene returns a
    finding on EVERY video, and any finding is a paid revision round. Deleting
    this paragraph wedges the pipeline; it does not tighten the review."""
    prompt = ai_review._REVIEW_PROMPT
    assert "Made with tubematic.ai" in prompt
    assert "THAT IS INTENTIONAL BRANDING AND IS CORRECT" in prompt
    assert "Do not report the watermark as a" in prompt
    # Scenes are never told about the mark, so content will sit under it.
    assert "visible through it or passes beneath it" in prompt
    # The mark can be switched off, and that must not become a finding either.
    assert "A video without the mark is likewise not a defect" in prompt


def test_the_prompt_asks_for_redundant_scene_text_as_a_suggestion():
    """The positive half: scene text restating the narration is the thing the
    captions replace. It is a suggestion rather than a must-fix because it is a
    quality call, not an unshippable defect."""
    prompt = ai_review._REVIEW_PROMPT
    assert "redundant_text" in prompt
    assert 'under "suggestions"' in prompt


def test_the_prompt_carves_out_text_that_carries_its_own_information():
    """Without this the reviewer flags a chart axis or a pinned label as
    redundant, which would make every diagram beat cost a revision round."""
    assert "not redundant and must not be reported" in ai_review._REVIEW_PROMPT


# ── the register block's two clauses (review follow-up) ─────────────────────
#
# They were one block, sent whenever a video could contain figures at all.
# That told an "illustrated" video — generated character artwork, line art
# explicitly excluded — that simple line-art stick figures were intended.

def test_an_illustrated_video_is_not_told_line_art_is_intended():
    block = ai_review._register_block("dark", figures=True, line_art=False)
    assert "line-art" not in block
    assert "placeholder" not in block


def test_an_illustrated_video_still_gets_the_held_pose_licence():
    """The half that must NOT be lost. Illustrated characters are posed
    discretely too, so without this a held pose reads as broken animation —
    and any finding routes the video to REVISION_REQUESTED, which would wedge
    the whole register rather than merely mis-grade it."""
    block = ai_review._register_block("dark", figures=True, line_art=False)
    assert "A held pose is correct" in block
    assert "jerky" in block


def test_a_stick_video_gets_both_clauses():
    block = ai_review._register_block("light", figures=True, line_art=True)
    assert "A held pose is correct" in block
    assert "line-art" in block


def test_a_figureless_video_gets_neither():
    block = ai_review._register_block("dark", figures=False, line_art=False)
    assert "A held pose is correct" not in block
    assert "line-art" not in block


def test_line_art_without_figures_cannot_leak_through():
    """line_art is meaningless without figures; the nesting must not let a
    stray True emit a clause about figures the video cannot contain."""
    block = ai_review._register_block("dark", figures=False, line_art=True)
    assert "line-art" not in block


# ── Usage returned for the caller to record (TMDEV-107) ──────────────────────
# The module is DB-free, so it hands the review's usage back rather than
# recording it. It must do so on every path where Gemini answered 200 — a
# reply that failed to parse was still billed — and on no path where it didn't.

_USAGE = {"promptTokenCount": 66000, "candidatesTokenCount": 300, "thoughtsTokenCount": 900,
          "promptTokensDetails": [{"modality": "VIDEO", "tokenCount": 65000},
                                  {"modality": "AUDIO", "tokenCount": 1000}]}


def test_usage_is_returned_with_a_clean_review(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    handler = _default_handler([], generate_body={**_CLEAN_BODY, "usageMetadata": _USAGE})
    monkeypatch.setattr(httpx, "Client", _make_client_factory(handler))

    result = ai_review.run_ai_review(str(video_file), {}, model="gemini-2.5-flash", fps=10)

    assert result["usage"] == {"model": "gemini-2.5-flash", "fps": 10, "usageMetadata": _USAGE}


def test_usage_is_returned_when_a_billed_reply_fails_to_parse(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    body = {"candidates": [{"content": {"parts": [{"text": "not json"}]}}], "usageMetadata": _USAGE}
    monkeypatch.setattr(httpx, "Client", _make_client_factory(
        _default_handler([], generate_body=body)))

    result = ai_review.run_ai_review(str(video_file), {})

    assert "error" in result
    assert result["usage"]["usageMetadata"] == _USAGE


def test_a_non_object_reply_fails_open_instead_of_raising(monkeypatch, video_file):
    """A JSON array used to escape the never-raises contract via result.get()."""
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    body = {"candidates": [{"content": {"parts": [{"text": "[1, 2]"}]}}], "usageMetadata": _USAGE}
    monkeypatch.setattr(httpx, "Client", _make_client_factory(
        _default_handler([], generate_body=body)))

    result = ai_review.run_ai_review(str(video_file), {})

    assert "error" in result and result["must_fix"] == []
    assert result["usage"] is not None


def test_no_usage_when_the_upload_fails_before_any_review(monkeypatch, video_file):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "Client", _make_client_factory(
        _default_handler([], generate_body=_CLEAN_BODY, file_states=("FAILED",))))

    result = ai_review.run_ai_review(str(video_file), {})

    assert "error" in result and "usage" not in result
