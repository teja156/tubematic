"""Unit tests for onboard/api_keys.py (TMDEV-52).

Every "invalid" case below replays the *observed* body each provider returned
to a deliberately bogus token, not a shape invented from a docs page. If a
provider changes its rejection wording these tests are the thing that should
break — that is the point of them.

Requests go through httpx.MockTransport rather than a monkeypatched `_send`,
so the header the checker actually sets, the method it uses and the body it
posts are all exercised for real.
"""
import httpx
import pytest

from onboard import api_keys
from onboard.api_keys import (
    INVALID,
    UNKNOWN,
    VALID,
    KeyCheck,
    check_elevenlabs,
    check_gemini,
    check_openai,
    check_postforme,
    check_youtube_transcript,
    resolve_secret,
)

# Observed 2026-09-01 by probing each endpoint with a bogus token.
ELEVENLABS_401 = {"detail": {"type": "authentication_error", "code": "unauthorized",
                             "message": "Invalid API key", "status": "invalid_api_key"}}
GEMINI_400 = {"error": {"code": 400,
                        "message": "API key not valid. Please pass a valid API key.",
                        "status": "INVALID_ARGUMENT",
                        "details": [{"@type": "type.googleapis.com/google.rpc.ErrorInfo",
                                     "reason": "API_KEY_INVALID",
                                     "domain": "googleapis.com"}]}}
OPENAI_401 = {"error": {"message": "Incorrect API key provided: bogus-ke*****ev52. You can find "
                                   "your API key at https://platform.openai.com/account/api-keys.",
                        "type": "invalid_request_error", "code": "invalid_api_key"}}
YT_401_TEXT = "Unauthorized, token is invalid"
# Observed 2026-09-05 by probing GET /v1/social-accounts with a bogus token.
# Note this one answers 401 *and* carries a machine-readable code — the code is
# the discriminator, not the status, for the same reason as Gemini's 400.
POSTFORME_401 = {"meta": {"requestId": "req_8MyIJ2G23"},
                 "error": {"code": "err:frontline:client:invalid_key",
                           "message": "Authentication failed. The provided API key is invalid."}}
# Sent with no Authorization header at all — a different code, same status.
POSTFORME_401_MISSING = {"meta": {"requestId": "req_uZ5z8AC3M"},
                         "error": {"code": "err:frontline:client:missing_credentials",
                                   "message": "Authentication required. Please provide a valid "
                                              "API key."}}


def transport(handler):
    return httpx.MockTransport(handler)


def responder(status, *, json=None, text=None, capture=None):
    """A MockTransport handler that records the request it saw."""
    def handle(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        if text is not None:
            return httpx.Response(status, text=text)
        return httpx.Response(status, json=json if json is not None else {})
    return handle


def raiser(exc):
    def handle(request: httpx.Request) -> httpx.Response:
        raise exc
    return handle


# ── ElevenLabs — key validity AND the four permissions Tubematic needs ──────

# Observed 2026-09-01: this is what an under-scoped (but real) key gets back.
def missing_perm(permission):
    return {"detail": {"status": "missing_permissions",
                       "message": f"The API key you used is missing the permission "
                                  f"{permission} to execute this operation."}}


def elevenlabs_router(by_path, capture=None):
    """Answer each of the four permission probes differently, keyed on path."""
    def handle(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        for fragment, (status, body) in by_path.items():
            if fragment in request.url.path:
                if isinstance(body, str):
                    return httpx.Response(status, text=body)
                return httpx.Response(status, json=body)
        return httpx.Response(200, json={})
    return handle


def test_elevenlabs_probes_every_required_permission():
    seen = []
    result = check_elevenlabs("real-key", transport=transport(elevenlabs_router({}, capture=seen)))
    assert result.status == VALID
    paths = [r.url.path for r in seen]
    assert paths == [
        "/v1/text-to-speech/zzzzINVALIDvoiceZZZZ",
        "/v1/voices",
        "/v1/studio/projects",
        "/v1/pronunciation-dictionaries",
    ]
    assert all(r.headers["xi-api-key"] == "real-key" for r in seen)


def test_the_tts_probe_names_a_voice_that_cannot_exist_so_no_audio_is_generated():
    """Auth runs before voice lookup (probed), so this never reaches
    generation — the check must never cost an ElevenLabs credit."""
    seen = []
    check_elevenlabs("real-key", transport=transport(elevenlabs_router(
        {"text-to-speech": (400, {"detail": {"status": "voice_not_found"}})}, capture=seen)))
    tts = seen[0]
    assert tts.method == "POST"
    assert "INVALID" in tts.url.path


def test_a_voice_not_found_from_the_tts_probe_means_the_permission_is_present():
    """The bogus voice is rejected *after* the permission gate, so a 4xx that
    isn't 401 proves text_to_speech is granted."""
    result = check_elevenlabs("real-key", transport=transport(elevenlabs_router(
        {"text-to-speech": (400, {"detail": {"status": "voice_not_found"}})})))
    assert result.status == VALID


def test_elevenlabs_rejects_a_key_missing_one_permission():
    result = check_elevenlabs("scoped", transport=transport(elevenlabs_router(
        {"/v1/voices": (401, missing_perm("voices_read"))})))
    assert result.status == INVALID
    assert "voices (read)" in result.detail
    assert "text-to-speech" not in result.detail


def test_every_missing_permission_is_reported_at_once():
    """Reporting them one per re-entry would make the hard gate a slog."""
    result = check_elevenlabs("scoped", transport=transport(elevenlabs_router({
        "/v1/studio/projects": (401, missing_perm("projects_read")),
        "/v1/pronunciation-dictionaries": (401, missing_perm("pronunciation_dictionaries_read")),
    })))
    assert result.status == INVALID
    assert "projects (read)" in result.detail
    assert "pronunciation dictionaries (read)" in result.detail


def test_a_fully_scoped_key_is_accepted():
    result = check_elevenlabs("good", transport=transport(elevenlabs_router({})))
    assert result.status == VALID
    assert result.detail == ""


def test_elevenlabs_rejects_a_bad_key_and_surfaces_its_message():
    result = check_elevenlabs("bad", transport=transport(responder(401, json=ELEVENLABS_401)))
    assert result.status == INVALID
    assert result.detail == "Invalid API key"


def test_a_wrong_key_short_circuits_instead_of_probing_all_four():
    """Every remaining probe would return the same thing."""
    seen = []
    check_elevenlabs("bad", transport=transport(
        responder(401, json=ELEVENLABS_401, capture=seen)))
    assert len(seen) == 1


def test_elevenlabs_401_without_the_expected_body_still_rejects():
    result = check_elevenlabs("bad", transport=transport(responder(401, text="nope")))
    assert result.status == INVALID
    assert result.detail == "Invalid API key."


def test_a_rate_limit_is_not_treated_as_proof_a_permission_is_granted():
    """A 429 can land before the permission gate, so unlike the single-shot
    checkers it is evidence of nothing here."""
    result = check_elevenlabs("real-key", transport=transport(elevenlabs_router(
        {"/v1/voices": (429, {})})))
    assert result.status == UNKNOWN
    assert "voices (read)" in result.detail


# ── Gemini — the regression this whole design turns on ──────────────────────

def test_gemini_rejects_a_bad_key_despite_answering_400_not_401():
    result = check_gemini("bad", transport=transport(responder(400, json=GEMINI_400)))
    assert result.status == INVALID
    assert result.detail == "API key not valid. Please pass a valid API key."


def test_gemini_400_without_api_key_invalid_is_unknown_not_invalid():
    """A 400 that isn't about the key (a malformed request, say) must not be
    reported as a bad key — the discriminator is the ErrorInfo reason, never
    the status code."""
    other_400 = {"error": {"code": 400, "message": "Invalid JSON payload.",
                           "status": "INVALID_ARGUMENT",
                           "details": [{"reason": "INVALID_ARGUMENT"}]}}
    result = check_gemini("real-key", transport=transport(responder(400, json=other_400)))
    assert result.status == UNKNOWN


def gemini_router(by_fragment, capture=None):
    """Answer the model listing and each capability probe separately."""
    def handle(request: httpx.Request) -> httpx.Response:
        if capture is not None:
            capture.append(request)
        for fragment, (status, body) in by_fragment.items():
            if fragment in request.url.path:
                return httpx.Response(status, json=body)
        if request.method == "GET":
            return httpx.Response(200, json={"models": []})
        return httpx.Response(400, json={"error": {"message": "contents is required"}})
    return handle


def test_gemini_accepts_a_working_key():
    seen = []
    result = check_gemini("real-key", transport=transport(gemini_router({}, capture=seen)))
    assert result.status == VALID
    assert seen[0].headers["x-goog-api-key"] == "real-key"
    assert "real-key" not in str(seen[0].url), "key must never travel in the URL (TMDEV-46)"


def test_gemini_probes_only_the_text_model_it_still_uses():
    """Gemini no longer draws images (TMDEV-165), so its image-quota family is
    no longer probed — a free-tier key must not be warned about a capability
    nothing asks it for."""
    seen = []
    check_gemini("real-key", transport=transport(gemini_router({}, capture=seen)))
    paths = [r.url.path for r in seen]
    assert paths == [
        "/v1beta/models",
        "/v1beta/models/gemini-2.5-flash:generateContent",
    ]
    assert all(r.method == "POST" and r.content == b"{}" for r in seen[1:]), \
        "capability probes must send an empty body so nothing is ever generated"


def test_a_key_without_text_quota_names_ai_review_and_mining():
    result = check_gemini("depleted", transport=transport(gemini_router(
        {"gemini-2.5-flash:": (429, {"error": {"code": 429}})})))
    assert result.status == UNKNOWN
    assert "AI review and topic mining" in result.detail


def test_a_capability_probe_that_cannot_be_reached_does_not_warn():
    """The key already proved itself on the listing call; a flaky follow-up
    request is evidence of nothing."""
    calls = []

    def handle(request):
        calls.append(request)
        if request.method == "GET":
            return httpx.Response(200, json={"models": []})
        raise httpx.ConnectError("flaky")

    result = check_gemini("real-key", transport=transport(handle))
    assert result.status == VALID
    assert len(calls) == 2


# ── OpenAI ──────────────────────────────────────────────────────────────────

def test_openai_probes_the_image_endpoint_it_actually_uses():
    """Not GET /v1/models — that needs api.model.read, which the pipeline never
    uses. The probe must be the same call generate_image makes."""
    seen = []
    result = check_openai("real-key", transport=transport(
        responder(400, json={"error": {"message": "Missing required parameter: 'prompt'."}},
                  capture=seen)))
    assert result.status == VALID, "a 400 on the empty body means auth+permission passed"
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/v1/images/generations"
    assert seen[0].headers["authorization"] == "Bearer real-key"
    assert seen[0].content in (b"{}", b'{}')


def test_openai_under_scoped_key_is_rejected_not_reported_as_verified():
    """The key authenticates but cannot generate images — which is the only
    thing Tubematic ever asks it to do. Showing "Key verified" here would be a
    false assurance that fails later inside generate_image."""
    body = {"error": {"message": "You have insufficient permissions for this operation. "
                                 "Missing scopes: image.request.",
                      "type": "invalid_request_error", "code": "insufficient_permissions"}}
    result = check_openai("scoped", transport=transport(responder(401, json=body)))
    assert result.status == INVALID
    assert "image generation" in result.detail


def test_openai_403_insufficient_permissions_is_also_rejected():
    body = {"error": {"message": "You have insufficient permissions for this operation."}}
    result = check_openai("scoped", transport=transport(responder(403, json=body)))
    assert result.status == INVALID
    assert "image generation" in result.detail


def test_openai_rejection_never_echoes_the_key_back():
    """OpenAI's own 401 message quotes a masked slice of the submitted key
    ('bogus-ke*****ev52') — twelve real characters of a live secret."""
    key = "bogus-key-tmdev52"
    result = check_openai(key, transport=transport(responder(401, json=OPENAI_401)))
    assert result.status == INVALID
    assert key not in result.detail
    assert "bogus-ke" not in result.detail
    assert "Incorrect API key provided" not in result.detail


def test_openai_rate_limit_is_not_proof_the_key_may_generate_images():
    result = check_openai("real-key", transport=transport(responder(429, json={})))
    assert result.status == UNKNOWN


# ── youtube-transcript.io ───────────────────────────────────────────────────

def test_youtube_transcript_probes_with_an_empty_id_list():
    """Nothing is fetched and no transcript quota is spent — the empty list is
    what makes this probe free."""
    seen = []
    result = check_youtube_transcript("real-key", transport=transport(
        responder(200, json=[], capture=seen)))
    assert result.status == VALID
    assert seen[0].method == "POST"
    assert seen[0].headers["authorization"] == "Basic real-key"
    assert b'"ids": []' in seen[0].content or b'"ids":[]' in seen[0].content


def test_youtube_transcript_rejects_a_bad_token_from_plain_text():
    result = check_youtube_transcript("bad", transport=transport(
        responder(401, text=YT_401_TEXT)))
    assert result.status == INVALID
    assert result.detail == YT_401_TEXT


def test_youtube_transcript_400_means_auth_passed_and_only_the_body_was_rejected():
    result = check_youtube_transcript("real-key", transport=transport(
        responder(400, text="ids must not be empty")))
    assert result.status == VALID


# ── Unproven never means invalid ────────────────────────────────────────────

ALL_CHECKERS = [check_elevenlabs, check_gemini, check_openai, check_youtube_transcript,
                check_postforme]


@pytest.mark.parametrize("check", ALL_CHECKERS)
@pytest.mark.parametrize("exc", [
    httpx.ConnectError("no route to host"),
    httpx.ConnectTimeout("timed out"),
    httpx.ReadTimeout("timed out"),
])
def test_transport_failures_are_unknown_so_an_offline_install_still_completes(check, exc):
    result = check("real-key", transport=transport(raiser(exc)))
    assert result.status == UNKNOWN
    assert "not verified" in result.detail


@pytest.mark.parametrize("check", ALL_CHECKERS)
def test_server_errors_are_unknown_not_invalid(check):
    result = check("real-key", transport=transport(responder(503, text="upstream down")))
    assert result.status == UNKNOWN


@pytest.mark.parametrize("check", ALL_CHECKERS)
def test_no_checker_ever_puts_the_key_in_the_message_it_returns(check):
    """Covers the rejection branches specifically, not just the fallbacks: a
    provider quoting the credential back in its own error text, printed to the
    terminal, is how a Gemini key leaked once already (TMDEV-46). Handlers a
    given checker doesn't recognise fall through to _accepted_or_unknown,
    which composes its own message, so this is safe to run across all four."""
    key = "sk-super-secret-value"
    handlers = (
        responder(401, json=OPENAI_401),
        responder(400, json=GEMINI_400),
        responder(503, text=key),
        raiser(httpx.ConnectError(key)),
        # Rejection bodies that quote the key back — one per service's own
        # invalid signature.
        responder(401, json={"detail": {"message": f"bad key {key}"}}),
        responder(400, json={"error": {"message": f"bad {key}",
                                       "details": [{"reason": "API_KEY_INVALID"}]}}),
        responder(401, text=f"Token {key} invalid"),
    )
    for handler in handlers:
        result = check(key, transport=transport(handler))
        assert key not in result.detail


def test_a_long_rejection_body_is_scrubbed_before_it_is_truncated():
    """Truncating first could split the key and leave its tail in the
    message — youtube-transcript.io's branch caps at 200 chars."""
    key = "sk-super-secret-value"
    body = "x" * 190 + key + " trailing"
    result = check_youtube_transcript(key, transport=transport(responder(401, text=body)))
    assert result.status == INVALID
    assert key not in result.detail
    # The leading fragment too: truncating first would keep "sk-super-s" and
    # only the tail would fall off the end.
    assert "sk-super" not in result.detail


# ── resolve_secret: the ask → check → re-ask loop ───────────────────────────

class _Recorder:
    def __init__(self):
        self.lines = []

    def __call__(self, status, detail):
        self.lines.append((status, detail))


def test_blank_is_returned_untouched_and_never_hits_the_network():
    """Three of the four keys are legitimately optional — validating "" would
    manufacture a spurious rejection on most fields."""
    calls = []
    report = _Recorder()
    assert resolve_secret(lambda k: calls.append(k), "", lambda: "", report) == ""
    assert calls == []
    assert report.lines == []


def test_surrounding_whitespace_is_stripped_from_the_stored_value():
    """The stripped value is what gets written to .env, so trimming only for
    the probe would verify one string and store another."""
    checked = []
    result = resolve_secret(lambda k: checked.append(k) or KeyCheck(VALID),
                            "  sk-real-key\n", _never_asked, _Recorder())
    assert result == "sk-real-key"
    assert checked == ["sk-real-key"]


@pytest.mark.parametrize("pasted", ["sk-key\nmore", "sk-key\rmore", "sk\x00key"])
def test_an_unsendable_key_is_invalid_not_unknown(pasted):
    """httpx raises LocalProtocolError for these, and LocalProtocolError
    subclasses httpx.HTTPError — so without the guard they were caught as
    "provider unreachable", classified UNKNOWN, and silently accepted."""
    checked = []
    answers = iter(["sk-clean-key"])
    report = _Recorder()
    result = resolve_secret(lambda k: checked.append(k) or KeyCheck(VALID),
                            pasted, lambda: next(answers), report)
    assert result == "sk-clean-key"
    assert report.lines[0][0] == INVALID
    assert checked == ["sk-clean-key"], "the malformed value must never reach the network"


def test_a_non_ascii_key_is_invalid_rather_than_crashing_the_wizard():
    """A non-ASCII header value raises UnicodeEncodeError, which is not an
    httpx error at all — it escaped the checker and took down the wizard."""
    report = _Recorder()
    result = resolve_secret(lambda k: KeyCheck(VALID), "sk-ké", lambda: "", report)
    assert result == ""
    assert report.lines[0][0] == INVALID


def test_interior_spaces_are_left_for_the_provider_to_reject():
    """httpx sends these fine, so a real rejection is more informative than a
    guess — the guard must not over-reject."""
    assert api_keys.malformed_reason("sk-key with spaces") == ""


def test_a_tab_is_reported_as_a_paste_artefact():
    """httpx would send it, but no provider issues keys containing a tab, so
    naming the artefact beats a generic 401."""
    assert "tab" in api_keys.malformed_reason("sk-key\twith-tab")


def test_a_valid_key_is_accepted_without_re_asking():
    report = _Recorder()
    result = resolve_secret(lambda k: KeyCheck(VALID), "good", _never_asked, report)
    assert result == "good"
    assert report.lines == [(VALID, "")]


def test_an_unknown_result_is_accepted_with_a_warning_not_a_retry():
    report = _Recorder()
    result = resolve_secret(lambda k: KeyCheck(UNKNOWN, "Could not reach X"),
                            "maybe", _never_asked, report)
    assert result == "maybe"
    assert report.lines == [(UNKNOWN, "Could not reach X")]


def test_an_invalid_key_is_re_asked_until_one_clears():
    answers = iter(["still-bad", "good"])
    checks = {"bad": KeyCheck(INVALID, "nope"), "still-bad": KeyCheck(INVALID, "nope"),
              "good": KeyCheck(VALID)}
    report = _Recorder()
    result = resolve_secret(lambda k: checks[k], "bad", lambda: next(answers), report)
    assert result == "good"
    assert [status for status, _ in report.lines] == [INVALID, INVALID, VALID]


def test_going_blank_on_a_re_ask_leaves_the_field_unset():
    """The deliberate way out for someone who can't produce a working key —
    apply_env's presence gate then decides whether unset is fatal."""
    report = _Recorder()
    result = resolve_secret(lambda k: KeyCheck(INVALID, "nope"), "bad", lambda: "", report)
    assert result == ""


def _never_asked():
    raise AssertionError("ask_again must not be called for a key that was not rejected")


# ── Every prompted secret is actually covered ───────────────────────────────

def test_every_secret_field_has_a_live_check():
    """The ticket's "all services" clause. A future provider added as a
    kind="secret" field without a checker fails here rather than shipping with
    its key silently unvalidated."""
    from onboard.config import SECTIONS

    unchecked = [f.key for s in SECTIONS for f in s.fields
                 if f.kind == "secret" and f.key_check is None]
    assert unchecked == []


def test_checkers_are_wired_to_the_right_services():
    from onboard.config import SECTIONS

    wired = {f.key: f.key_check for s in SECTIONS for f in s.fields if f.kind == "secret"}
    assert wired == {
        "ELEVENLABS_API_KEY": api_keys.check_elevenlabs,
        "GEMINI_API_KEY": api_keys.check_gemini,
        "OPENAI_API_KEY": api_keys.check_openai,
        "YOUTUBE_TRANSCRIPT_API_KEY": api_keys.check_youtube_transcript,
        "POSTFORME_API_KEY": api_keys.check_postforme,
    }


# ── postforme.dev (TMDEV-83) ────────────────────────────────────────────────

def test_postforme_accepts_a_good_key():
    assert check_postforme("real", transport=transport(
        responder(200, json={"data": []}))).status == VALID


def test_postforme_rejects_a_bad_key_on_the_error_code_not_the_status():
    """Every provider here needs its own discriminator. A shared "401 means
    invalid" rule would be wrong for Gemini (which answers 400) and is wrong
    here in the other direction: postforme answers 401 for a *missing* key too,
    which is a caller bug rather than a bad credential."""
    result = check_postforme("bogus", transport=transport(responder(401, json=POSTFORME_401)))
    assert result.status == INVALID
    assert "invalid" in result.detail.lower()


def test_postforme_treats_a_missing_credential_401_as_unverified_not_invalid():
    """Reaching this means the checker failed to send the header — the key it
    was handed was never actually judged, so calling it invalid would reject a
    perfectly good key on our own bug."""
    result = check_postforme("real", transport=transport(
        responder(401, json=POSTFORME_401_MISSING)))
    assert result.status == UNKNOWN


def test_postforme_sends_the_key_as_a_bearer_header_and_never_in_the_url():
    seen = []
    check_postforme("real-key", transport=transport(
        responder(200, json={"data": []}, capture=seen)))
    assert seen[0].headers["Authorization"] == "Bearer real-key"
    assert "real-key" not in str(seen[0].url)
    assert seen[0].method == "GET"


def test_postforme_probe_is_read_only():
    """A checker that published something while validating a key would be a
    catastrophic surprise. Pin the endpoint, not just the method."""
    seen = []
    check_postforme("real", transport=transport(responder(200, json={"data": []}, capture=seen)))
    assert seen[0].url.path == "/v1/social-accounts"
    assert seen[0].method == "GET"
