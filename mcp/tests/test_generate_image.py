"""Tests for the generate_image MCP tool (TMDEV-29).

Requires the mcp/ package deps (fastmcp, httpx) — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import base64
import json
from datetime import datetime, timezone

import pytest

import server

VID = "vid-1"
PNG = b"\x89PNG\r\n\x1a\nfake"
B64 = base64.b64encode(PNG).decode()


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@pytest.fixture
def env(tmp_path, monkeypatch):
    """Throwaway DB + jobs dir, with a video row and both keys configured —
    the Gemini one so the redaction tests can prove it is scrubbed too."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    monkeypatch.setattr(server, "JOBS_DIR", tmp_path / "jobs")
    monkeypatch.setattr(server, "_gemini_key", lambda: "gemini-secret-key")
    monkeypatch.setattr(server, "_openai_key", lambda: "openai-secret-key")
    server._init_db()
    with server._conn() as con:
        con.execute(
            "INSERT INTO videos (id, topic, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (VID, "test topic", _now(), _now()),
        )
    return tmp_path


class _Resp:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def _stub_post(monkeypatch, resp, capture=None):
    """Replace httpx.Client with one whose .post returns `resp`."""
    import httpx

    class _Client:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def post(self, url, headers=None, json=None):
            if capture is not None:
                capture.update({"url": url, "headers": headers or {}, "json": json or {}})
            if isinstance(resp, Exception):
                raise resp
            return resp

    monkeypatch.setattr(httpx, "Client", _Client)


def _openai_payload(b64=B64, usage=None):
    payload = {"data": [{"b64_json": b64}]}
    if usage is not None:
        payload["usage"] = usage
    return payload


# ── Happy path ────────────────────────────────────────────────────────────────

def test_writes_image_and_returns_public_path(env, monkeypatch):
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()))

    out = server.generate_image(VID, "skyline", "a city at dusk")

    assert out["public_path"] == f"/public/{VID}/images/skyline.png"
    assert (env / "jobs" / VID / "images" / "skyline.png").read_bytes() == PNG
    assert out["size_bytes"] == len(PNG)
    assert (out["provider"], out["model"]) == ("openai", "gpt-image-2.5-flare")


def test_an_unset_image_model_uses_the_openai_default(env, monkeypatch):
    """Images come from OpenAI whatever is stored: the default needs no row."""
    capture = {}
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()), capture)
    server.generate_image(VID, "skyline", "a city at dusk")
    assert capture["url"] == server.OPENAI_IMAGES_URL
    assert capture["json"]["model"] == server.DEFAULT_IMAGE_MODEL == "gpt-image-2.5-flare"


@pytest.mark.parametrize("aspect,size", [
    ("9:16", "1088x1920"), ("1:1", "1024x1024"), ("16:9", "1920x1088"),
])
def test_aspect_ratio_is_sent_as_the_mapped_size(env, monkeypatch, aspect, size):
    """TMDEV-69's lesson: assert the caller's value reaches the provider, using
    non-default ratios too — "9:16" alone would pass against a hardcoded size."""
    capture = {}
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()), capture)
    server.generate_image(VID, "skyline", "a city at dusk", aspect_ratio=aspect)
    assert capture["json"]["size"] == size


def test_api_key_goes_in_a_header_not_the_url(env, monkeypatch):
    """httpx embeds the request URL in its error strings, and those reach the
    dashboard-visible comments table — TMDEV-46."""
    capture = {}
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()), capture)

    server.generate_image(VID, "skyline", "a city at dusk")

    assert capture["headers"]["Authorization"] == "Bearer openai-secret-key"
    assert "openai-secret-key" not in capture["url"]


def _usage_events():
    with server._conn() as con:
        return con.execute(
            "SELECT e.*, l.video_id FROM usage_events e "
            "LEFT JOIN usage_event_videos l ON l.event_id = e.id").fetchall()


def test_generate_image_records_a_billed_reply_with_no_image(env, monkeypatch):
    """A 200 with no image data was still billed — recorded before the check."""
    payload = {"data": [], "usage": {"input_tokens": 12, "output_tokens": 0}}
    _stub_post(monkeypatch, _Resp(payload=payload))
    assert "error" in server.generate_image(VID, "skyline", "a city at dusk")
    assert len(_usage_events()) == 1


def test_generate_image_records_nothing_for_an_error_status(env, monkeypatch):
    _stub_post(monkeypatch, _Resp(status_code=429, text="quota"))
    assert "error" in server.generate_image(VID, "skyline", "a city at dusk")
    assert _usage_events() == []


# ── Sizes and usage ───────────────────────────────────────────────────────────

def test_openai_size_dimensions_are_divisible_by_16(env):
    """OpenAI's image models reject sizes that aren't — which rules out the Shorts-native
    1080x1920, since 1080/16 is 67.5."""
    for size in server.OPENAI_SIZE_BY_ASPECT.values():
        w, h = (int(x) for x in size.split("x"))
        assert w % 16 == 0 and h % 16 == 0, size


def test_openai_records_its_usage_split_into_text_and_image_tokens(env, monkeypatch):
    server._set_setting("image_model", "gpt-image-2.5-flare")
    usage = {"input_tokens": 40, "output_tokens": 4160,
             "input_tokens_details": {"text_tokens": 40, "image_tokens": 0}}
    _stub_post(monkeypatch, _Resp(payload={"data": [{"b64_json": B64}], "usage": usage}))
    assert "error" not in server.generate_image(VID, "skyline", "a city at dusk")
    [event] = _usage_events()
    assert (event["service"], event["model"], event["video_id"]) == ("openai", "gpt-image-2.5-flare", VID)
    assert json.loads(event["units"]) == {"input": 40, "output_image": 4160}
    assert json.loads(event["raw_usage"]) == usage


# ── Guards ────────────────────────────────────────────────────────────────────

def test_unknown_video_is_rejected(env, monkeypatch):
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()))
    assert "not found" in server.generate_image("nope", "skyline", "x")["error"]


@pytest.mark.parametrize("name", ["", "../escape", "with space", "with/slash", "-leading"])
def test_invalid_image_names_are_rejected(env, name):
    assert "image_name" in server.generate_image(VID, name, "x")["error"]


def test_an_image_name_with_no_room_for_its_extension_is_refused_before_the_call(env, monkeypatch):
    """The name is checked against the longest image extension the tool knows
    (".webp") before the paid call, or a billed image could never be written."""
    capture = {}
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()), capture)
    assert "image_name" in server.generate_image(VID, "x" * 251, "x")["error"]
    assert capture == {}
    out = server.generate_image(VID, "x" * 250, "x")
    assert (env / "jobs" / VID / "images" / out["filename"]).read_bytes() == PNG


def test_empty_prompt_is_rejected(env):
    assert "prompt" in server.generate_image(VID, "skyline", "   ")["error"]


def test_missing_openai_key_is_reported_before_any_call(env, monkeypatch):
    """OpenAI is the only image provider, so there is no other key to fall back
    to — a Gemini key alone must not reach a call."""
    monkeypatch.setattr(server, "_openai_key", lambda: "")
    capture = {}
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()), capture)
    err = server.generate_image(VID, "skyline", "x")["error"]
    assert "OpenAI API key not set" in err
    # The remedy must name where the key actually lives now (TMDEV-73), not .env,
    # and must not point at the retired image_provider setting.
    assert "Settings" in err and ".env" not in err and "image_provider" not in err
    assert capture == {}


@pytest.mark.parametrize("aspect", ["7:3", "4:3", "2:3", "21:9"])
def test_an_unsupported_aspect_ratio_is_refused_before_any_call(env, monkeypatch, aspect):
    """Gemini took ten ratios; OpenAI's sizes cover three. A ratio only Gemini
    took is refused with the list, not sent."""
    capture = {}
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()), capture)
    err = server.generate_image(VID, "skyline", "x", aspect_ratio=aspect)["error"]
    assert err == (f"aspect_ratio {aspect!r} not supported — "
                   "expected one of ['16:9', '1:1', '9:16']")
    assert capture == {}


@pytest.mark.parametrize("stored", ["gemini-2.5-flash-image", "gpt-image-2", "nonsense"])
def test_a_stored_model_outside_the_catalog_is_refused_before_any_call(env, monkeypatch, stored):
    """The MCP server reads image_model raw — migration 0016 is what rewrites a
    stored Gemini model, and this is the backstop if one survives."""
    server._set_setting("image_model", stored)
    capture = {}
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()), capture)
    err = server.generate_image(VID, "skyline", "a city at dusk")["error"]
    assert f"image_model {stored!r} is not an available image model" in err
    assert "Settings → Images" in err
    assert capture == {}


def test_empty_response_is_reported_not_crashed(env, monkeypatch):
    _stub_post(monkeypatch, _Resp(payload={"data": []}))
    assert "no image data" in server.generate_image(VID, "skyline", "x")["error"]


def test_nothing_is_written_when_the_call_fails(env, monkeypatch):
    _stub_post(monkeypatch, _Resp(status_code=500, text="boom"))
    assert "error" in server.generate_image(VID, "skyline", "x")
    assert not (env / "jobs" / VID / "images").exists()


def test_rejected_when_claimed_by_another_session(env, monkeypatch):
    """TMDEV-61: a video already claimed by a different session is rejected
    before any paid OpenAI call — capture stays empty proves the fake
    transport was never invoked, not just that the tool returned an error."""
    capture = {}
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()), capture=capture)
    # A real (non-"no-session") calling identity — a bare call resolves to the
    # no-session fallback, which never checks or holds a claim by design, so
    # rejecting-as-a-non-owner needs a real owner on the calling side too.
    monkeypatch.setattr(server, "_session_owner", lambda: "session:me")
    server._release_scene_claim(VID)  # VID is reused across this module; clear any earlier claim first
    assert server._try_claim_scene_work(VID, "session:other") is None  # pre-claim by another owner
    try:
        result = server.generate_image(VID, "skyline", "x")
        assert result["error"] == "scene_work_claimed"
        assert result["claimed_by"] == "session:other"
        assert capture == {}
    finally:
        # _scene_claims is module-global and VID is reused across this file's
        # other tests — leaving this claim in place would reject every
        # generate_image call after this one for the rest of the suite.
        server._release_scene_claim(VID)


# ── Key redaction ─────────────────────────────────────────────────────────────

def test_key_is_redacted_from_http_error_bodies(env, monkeypatch):
    _stub_post(monkeypatch, _Resp(status_code=400,
                                  text="bad key openai-secret-key rejected"))
    err = server.generate_image(VID, "skyline", "x")["error"]
    assert "openai-secret-key" not in err
    assert "REDACTED" in err


def test_key_is_redacted_from_exception_strings(env, monkeypatch):
    """This is the TMDEV-46 shape: httpx puts the request URL in its error
    string, and the tool's error dict gets posted as a dashboard comment."""
    _stub_post(monkeypatch, RuntimeError(
        "connect failed for https://x/images?key=openai-secret-key"))
    err = server.generate_image(VID, "skyline", "x")["error"]
    assert "openai-secret-key" not in err


def test_both_provider_keys_are_redacted(env, monkeypatch):
    _stub_post(monkeypatch, _Resp(status_code=400,
                                  text="openai-secret-key and gemini-secret-key"))
    err = server.generate_image(VID, "skyline", "x")["error"]
    assert "openai-secret-key" not in err and "gemini-secret-key" not in err


# ── Contract with the rest of the pipeline ────────────────────────────────────

def test_returned_public_path_passes_validate_job(env, monkeypatch):
    """The whole point of returning public_path is that copying it verbatim
    into scene props validates — these two must not drift apart."""
    _stub_post(monkeypatch, _Resp(payload=_openai_payload()))
    out = server.generate_image(VID, "skyline", "a city at dusk")

    cfg = {"scenes": [{"type": "generated", "src": "hero",
                       "props": {"src": out["public_path"]}}]}
    assert server._bad_image_refs(cfg, VID) == []


# ── Failures reach the log (TMDEV-126) ────────────────────────────────────────
# A provider failure is returned, not raised, so it used to log as a plain
# successful call. Driven through the real server so the middleware runs.

def test_an_openai_429_is_one_error_line_naming_the_provider(env, monkeypatch, through_mcp):
    body = '{"error": {"code": "billing_hard_limit_reached", "message": "Billing limit reached."}}'
    _stub_post(monkeypatch, _Resp(status_code=429, text=body))
    out, (rec,) = through_mcp("generate_image", video_id=VID, image_name="skyline",
                              prompt="a city at dusk")
    assert out == {"error": f"OpenAI 429: {body}"}  # the tool's contract is unchanged
    assert rec.levelname == "ERROR" and rec.outcome == "error"
    assert (rec.provider_service, rec.provider_status, rec.provider_operation) == \
        ("openai", 429, "image")
    assert rec.provider_model == "gpt-image-2.5-flare"
    assert rec.video_id == VID
    assert "Billing limit reached" in rec.provider_body


def test_a_billed_reply_with_no_image_is_a_provider_failure(env, monkeypatch, through_mcp):
    """A 200 is no proof of success — no status check would ever reveal this."""
    _stub_post(monkeypatch, _Resp(payload={"data": []}))
    out, (rec,) = through_mcp("generate_image", video_id=VID, image_name="skyline",
                              prompt="a city at dusk")
    assert "no image data" in out["error"]
    assert rec.levelname == "ERROR"
    assert (rec.provider_service, rec.provider_status) == ("openai", 200)


def test_an_openai_error_status_is_logged_against_openai(env, monkeypatch, through_mcp):
    server._set_setting("image_model", "gpt-image-2.5-flare")
    _stub_post(monkeypatch, _Resp(status_code=500, text="upstream exploded"))
    out, (rec,) = through_mcp("generate_image", video_id=VID, image_name="skyline",
                              prompt="a city at dusk")
    assert out == {"error": "OpenAI 500: upstream exploded"}
    assert (rec.levelname, rec.provider_service, rec.provider_status) == ("ERROR", "openai", 500)


def test_a_project_without_model_access_gets_an_actionable_error(env, monkeypatch, through_mcp):
    """OpenAI grants model access per project, and its catalog lists a model the
    project still cannot call — so the raw 403 must become something a human
    can act on, naming the project and the model."""
    server._set_setting("image_model", "gpt-image-2.5-sunburst")
    body = {"error": {"message": "Project proj_Zz81 does not have access to model "
                                 "gpt-image-2.5-sunburst", "code": "model_not_found"}}
    _stub_post(monkeypatch, _Resp(status_code=403, payload=body, text=json.dumps(body)))
    out, (rec,) = through_mcp("generate_image", video_id=VID, image_name="skyline",
                              prompt="a city at dusk")
    assert "project proj_Zz81 has no access to gpt-image-2.5-sunburst" in out["error"]
    assert (rec.levelname, rec.provider_status) == ("ERROR", 403)


def test_a_request_that_never_got_a_response_is_logged(env, monkeypatch, through_mcp):
    """Timeouts, connection errors — and a non-ASCII pasted key, whose
    UnicodeEncodeError is not an httpx exception at all."""
    _stub_post(monkeypatch, UnicodeEncodeError("ascii", "é", 0, 1, "ordinal not in range"))
    out, (rec,) = through_mcp("generate_image", video_id=VID, image_name="skyline",
                              prompt="a city at dusk")
    assert out["error"].startswith("Image generation failed:")
    assert rec.levelname == "ERROR"
    assert rec.provider_status is None
    assert "UnicodeEncodeError" in rec.provider_body


def test_an_undecodable_200_is_reported_as_http_200_not_as_no_response(env, monkeypatch, through_mcp):
    """The reply arrived and was billed; only its image data was broken."""
    _stub_post(monkeypatch, _Resp(payload=_openai_payload("!!not base64!!")))
    out, (rec,) = through_mcp("generate_image", video_id=VID, image_name="skyline",
                              prompt="a city at dusk")
    assert out["error"].startswith("Could not decode image data")
    assert (rec.levelname, rec.provider_status) == ("ERROR", 200)
    assert "no response" not in rec.getMessage()


def test_a_malformed_json_200_is_reported_as_http_200(env, monkeypatch, through_mcp):
    class _BadJson(_Resp):
        def json(self):
            raise ValueError("Expecting value: line 1 column 1")

    _stub_post(monkeypatch, _BadJson(text="<html>gateway</html>"))
    out, (rec,) = through_mcp("generate_image", video_id=VID, image_name="skyline",
                              prompt="a city at dusk")
    assert out["error"].startswith("Image generation failed:")
    assert (rec.levelname, rec.provider_status) == ("ERROR", 200)
    assert "gateway" in rec.provider_body


def test_a_refusal_before_any_call_is_a_warning_not_an_incident(env, through_mcp):
    out, (rec,) = through_mcp("generate_image", video_id=VID, image_name="skyline", prompt="  ")
    assert out == {"error": "prompt must not be empty"}
    assert (rec.levelname, rec.outcome) == ("WARNING", "error")
    assert not hasattr(rec, "provider_service")
