"""The MCP tool-call middleware (TMDEV-86).

A FastMCP middleware rather than a decorator on each @mcp.tool, so these tests
exercise the one place every tool call goes through.
"""
import asyncio
import logging
import types

import pytest

import server


def _context(name, arguments=None):
    return types.SimpleNamespace(
        message=types.SimpleNamespace(name=name, arguments=arguments or {})
    )


def _run(middleware, context, call_next):
    return asyncio.run(middleware.on_call_tool(context, call_next))


async def _ok(_context):
    return "result"


@pytest.fixture
def logged(caplog):
    caplog.set_level(logging.INFO, logger="mcp")
    return caplog


def test_a_successful_call_is_logged_once_with_the_tool_name(logged):
    assert _run(server._ToolCallLogger(), _context("generate_voice"), _ok) == "result"
    (rec,) = [r for r in logged.records if r.name == "mcp"]
    assert rec.tool == "generate_voice"
    assert rec.levelname == "INFO"
    assert isinstance(rec.duration_ms, int)


def test_argument_values_are_dropped_but_their_keys_are_kept(logged):
    """Tool arguments routinely carry whole scripts, prompts and scene source.
    Keys keep the call's shape legible without any of that reaching disk."""
    secret_ish = "the entire 450-word script, verbatim"
    _run(server._ToolCallLogger(),
         _context("write_scene_file", {"scene_name": "intro", "content": secret_ish}), _ok)
    (rec,) = [r for r in logged.records if r.name == "mcp"]
    assert rec.arg_keys == ["content", "scene_name"]
    assert secret_ish not in str(vars(rec))


def test_video_and_profile_ids_pass_through_by_allowlist(logged):
    """They are what make a record findable from the dashboard's per-video tab.
    An allowlist, not a blocklist — otherwise the next large argument someone
    adds leaks by default."""
    _run(server._ToolCallLogger(),
         _context("submit_render", {"video_id": "vid_abc", "notes": "x" * 500}), _ok)
    (rec,) = [r for r in logged.records if r.name == "mcp"]
    assert rec.video_id == "vid_abc"
    assert not hasattr(rec, "notes")


def test_a_non_string_video_id_is_not_promoted(logged):
    """The filter is `video_id == <string>`; a non-string would never match and
    would put an arbitrary object into the record."""
    _run(server._ToolCallLogger(), _context("t", {"video_id": {"nested": 1}}), _ok)
    (rec,) = [r for r in logged.records if r.name == "mcp"]
    assert not hasattr(rec, "video_id")


def test_a_failing_tool_logs_at_error_and_the_exception_still_propagates(logged):
    """Logging must observe the failure, never swallow it — the agent has to
    keep seeing the error it would have seen without this middleware."""
    async def boom(_context):
        raise ValueError("nope")

    with pytest.raises(ValueError, match="nope"):
        _run(server._ToolCallLogger(), _context("generate_image"), boom)
    (rec,) = [r for r in logged.records if r.name == "mcp"]
    assert rec.levelname == "ERROR"
    assert rec.tool == "generate_image"


def test_the_middleware_is_actually_registered_on_the_server():
    """The class existing proves nothing about it being wired up."""
    assert any(isinstance(m, server._ToolCallLogger) for m in server.mcp.middleware)


def test_the_secret_provider_returns_a_list_and_never_raises(tmp_path, monkeypatch):
    """It is called from inside the log formatter, where raising would recurse."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "absent.db")
    assert server._log_secret_provider() == []


# ── Returned errors and provider failures (TMDEV-126) ───────────────────────
#
# A tool that fails by *returning* {"error": ...} used to log exactly like a
# success, so a depleted Gemini balance left nothing in any log. These run a
# throwaway FastMCP server carrying the real middleware, so the result the
# middleware inspects is the real ToolResult FastMCP builds — not a guess at
# its shape.

from fastmcp import Client, FastMCP  # noqa: E402
from fastmcp.server.middleware import Middleware  # noqa: E402

from tubematic_core import logging as tlog  # noqa: E402


class _Resp:
    def __init__(self, status_code, text):
        self.status_code = status_code
        self.text = text


def _throwaway_server():
    """A FastMCP server with the real middleware, plus a recorder (added
    first, so it runs innermost) that keeps each raw ToolResult."""
    seen = []

    class _Recorder(Middleware):
        async def on_call_tool(self, context, call_next):
            result = await call_next(context)
            seen.append(result)
            return result

    app = FastMCP("t")
    app.add_middleware(server._ToolCallLogger())
    app.add_middleware(_Recorder())

    @app.tool
    def refuses(video_id: str = "") -> dict:
        return {"error": "Domain 'x' is paused"}

    @app.tool
    def refuses_with_detail() -> dict:
        return {"error": "scene_work_claimed", "detail": "another session is working on it"}

    @app.tool
    def succeeds() -> dict:
        return {"ok": True, "error_count": 0}

    @app.tool
    def says_hello() -> str:
        return "hello"

    @app.tool
    def lists() -> list:
        return [{"error": "a list item is data, not a failure"}]

    @app.tool
    def provider_429(video_id: str = "") -> dict:
        server._provider_failed("gemini", "gemini-2.5-flash-image", "image",
                                resp=_Resp(429, '{"error": {"message": "prepayment credits are depleted"}}'))
        return {"error": "Gemini 429: depleted"}

    @app.tool
    def partial() -> dict:
        server._provider_failed("gemini", "gemini-2.5-flash", "mining",
                                resp=_Resp(503, "unavailable"), detail="https://youtu.be/a")
        server._provider_failed("gemini", "gemini-2.5-flash", "mining",
                                resp=_Resp(429, "quota"), detail="https://youtu.be/b")
        return {"proposed": 0, "skipped": 2}

    @app.tool
    def async_provider_failure() -> dict:
        server._provider_failed("openai", "gpt-image-2.5-flare", "image", error="ReadTimeout: timed out")
        return {"error": "Image generation failed: timed out"}

    @app.tool
    def leaks(secret: str) -> dict:
        server._provider_failed("gemini", "m", "image",
                                resp=_Resp(400, f"bad key {secret} and AIzaSyA1234567890abcdefghijklmn"))
        return {"error": f"Gemini 400: {secret} AIzaSyA1234567890abcdefghijklmn"}

    @app.tool
    def long_error() -> dict:
        return {"error": "x" * 5000}

    @app.tool
    def raises() -> dict:
        raise ValueError("nope")

    return app, seen


def _call(app, tool, logged, **arguments):
    logged.clear()

    async def go():
        async with Client(app) as client:
            return await client.call_tool(tool, arguments, raise_on_error=False)

    result = asyncio.run(go())
    return result, [r for r in logged.records if r.name == "mcp"]


def test_returned_error_reads_the_real_tool_result():
    app, seen = _throwaway_server()
    for tool in ("refuses", "refuses_with_detail", "succeeds", "says_hello", "lists"):
        asyncio.run(_client_call(app, tool))
    by_tool = dict(zip(("refuses", "refuses_with_detail", "succeeds", "says_hello", "lists"), seen))
    assert server._returned_error(by_tool["refuses"]) == "Domain 'x' is paused"
    assert server._returned_error(by_tool["refuses_with_detail"]) == \
        "scene_work_claimed — another session is working on it"
    assert server._returned_error(by_tool["succeeds"]) is None
    assert server._returned_error(by_tool["says_hello"]) is None
    # A list tool's items are data; only a returned dict's own `error` is a failure.
    assert server._returned_error(by_tool["lists"]) is None


async def _client_call(app, tool, **arguments):
    async with Client(app) as client:
        return await client.call_tool(tool, arguments, raise_on_error=False)


@pytest.mark.parametrize("weird", [None, "text", 42, object(), types.SimpleNamespace(
    structured_content={"result": "not a dict"})])
def test_returned_error_never_raises_on_an_unexpected_shape(weird):
    assert server._returned_error(weird) is None


def test_returned_error_survives_an_attribute_that_raises():
    class Hostile:
        @property
        def structured_content(self):
            raise RuntimeError("boom")

    assert server._returned_error(Hostile()) is None


def test_a_refusal_with_no_provider_call_is_one_warning(logged):
    """Paused domain, frozen field, empty prompt: worth seeing, not an incident."""
    app, _ = _throwaway_server()
    result, (rec,) = _call(app, "refuses", logged, video_id="vid_1")
    assert result.structured_content == {"error": "Domain 'x' is paused"}
    assert rec.levelname == "WARNING"
    assert rec.outcome == "error"
    assert "Domain 'x' is paused" in rec.getMessage()
    assert rec.video_id == "vid_1"
    assert not any(k.startswith("provider_") for k in vars(rec))


def test_a_provider_failure_is_one_error_line_carrying_the_provider_fields(logged):
    """The acceptance case: a Gemini 429 inside generate_image. One line, not a
    call-site line plus a middleware line."""
    app, _ = _throwaway_server()
    result, (rec,) = _call(app, "provider_429", logged, video_id="vid_9")
    assert result.structured_content == {"error": "Gemini 429: depleted"}
    assert rec.levelname == "ERROR"
    assert rec.outcome == "error"
    assert rec.video_id == "vid_9"
    assert (rec.provider_service, rec.provider_status, rec.provider_model,
            rec.provider_operation) == ("gemini", 429, "gemini-2.5-flash-image", "image")
    assert "prepayment credits are depleted" in rec.provider_body
    # The dashboard's Logs page renders the message alone, so the details
    # have to be in it, not only in the extra fields.
    message = rec.getMessage()
    for part in ("gemini", "gemini-2.5-flash-image", "HTTP 429", "prepayment credits are depleted"):
        assert part in message


def test_a_provider_failure_with_no_response_still_names_the_provider(logged):
    """Timeouts and connection errors raise before a response exists."""
    app, _ = _throwaway_server()
    _, (rec,) = _call(app, "async_provider_failure", logged)
    assert rec.levelname == "ERROR"
    assert rec.provider_status is None
    assert rec.provider_body == "ReadTimeout: timed out"
    assert "no response" in rec.getMessage()


def test_a_successful_call_with_failed_provider_calls_is_partial(logged):
    """Mining carries on past a failed URL and returns success. The failures
    must still surface — as the call's one line, with the latest failure and
    a count, not as a line per URL on top of it."""
    app, _ = _throwaway_server()
    result, (rec,) = _call(app, "partial", logged)
    assert result.structured_content == {"proposed": 0, "skipped": 2}
    assert rec.levelname == "ERROR"
    assert rec.outcome == "partial"
    assert rec.provider_failures == 2
    assert (rec.provider_status, rec.provider_detail) == (429, "https://youtu.be/b")
    assert "https://youtu.be/b" in rec.getMessage()
    assert "2 failed provider calls" in rec.getMessage()


def test_success_is_still_exactly_one_info_line(logged):
    app, _ = _throwaway_server()
    result, (rec,) = _call(app, "succeeds", logged)
    assert result.structured_content == {"ok": True, "error_count": 0}
    assert rec.levelname == "INFO"
    assert rec.outcome == "ok"
    assert rec.getMessage() == "tool succeeds"


def test_a_raised_exception_is_one_error_line_with_its_outcome(logged):
    app, _ = _throwaway_server()
    result, (rec,) = _call(app, "raises", logged)
    assert result.is_error
    assert rec.levelname == "ERROR"
    assert rec.outcome == "exception"


def test_a_long_returned_error_is_truncated_in_the_log(logged):
    app, _ = _throwaway_server()
    result, (rec,) = _call(app, "long_error", logged)
    assert result.structured_content == {"error": "x" * 5000}  # the return is untouched
    assert len(rec.getMessage()) < 700


def test_no_credential_reaches_the_log_line_on_any_sink(logged, tmp_path, monkeypatch):
    """Redacted in the record itself — not only by the JSONL formatter — because
    the stdout sink behind `docker logs` has no redacting formatter. Both axes:
    a stored key that appears bare, and a provider-shaped key never stored."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "t.db")
    server._init_db()
    stored = "stored-secret-value-4f9a2c"
    server._set_setting("gemini_api_key", stored)
    app, _ = _throwaway_server()
    result, (rec,) = _call(app, "leaks", logged, secret=stored)

    assert stored in result.structured_content["error"]  # the return is unchanged
    on_disk = tlog.JsonlFormatter("mcp", server._log_secret_provider).format(rec)
    for text in (rec.getMessage(), rec.provider_body, on_disk):
        assert stored not in text
        assert "AIzaSyA1234567890abcdefghijklmn" not in text


def test_the_helper_outside_a_tool_call_is_a_no_op():
    """A direct call from a script or a unit test has no holder to write to."""
    server._provider_failed("gemini", "m", "image", resp=_Resp(500, "x"))


def test_a_key_supplied_only_through_the_environment_is_redacted(logged, tmp_path, monkeypatch):
    """The key getters fall back to the environment, where the stored-value
    axis cannot see the key, and a bare value matches no pattern."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "absent.db")
    env_only = "env-only-openai-value-77c1"
    monkeypatch.setenv("OPENAI_API_KEY", env_only)
    app, _ = _throwaway_server()
    _, (rec,) = _call(app, "leaks", logged, secret=env_only)
    assert env_only not in rec.getMessage()
    assert env_only not in rec.provider_body


def test_a_key_straddling_the_length_limit_is_still_redacted(logged, tmp_path, monkeypatch):
    """Redact first, then cut. Cutting first leaves a partial key that no
    longer matches the stored value, and most of it would reach the log."""
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "t.db")
    server._init_db()
    stored = "stored-secret-value-4f9a2c-0123456789"
    server._set_setting("gemini_api_key", stored)
    # The key starts 10 characters before each limit, so a cut-first
    # implementation keeps exactly its first 10 characters.
    body = "b" * (server.PROVIDER_BODY_LOG_MAX - 10) + stored
    error = "e" * (server.RETURNED_ERROR_LOG_MAX - 10) + stored
    assert "stored-sec" not in server._log_safe(body, server.PROVIDER_BODY_LOG_MAX)
    assert "stored-sec" not in server._log_safe(error, server.RETURNED_ERROR_LOG_MAX)
    assert len(server._log_safe(body, server.PROVIDER_BODY_LOG_MAX)) <= server.PROVIDER_BODY_LOG_MAX
