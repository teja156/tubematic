"""Wire-level and composition tests for discord_notify.py (TMDEV-5).

Modelled on test_postforme.py: httpx.MockTransport means real httpx.Request
objects reach the assertions, so the URL actually posted to is exercised rather
than assumed.

Three things here are load-bearing:

  * **Redaction.** The webhook URL is a credential — anyone holding it can post
    to that channel. httpx puts the request URL in its exception text, and
    worker.py persists exception text into the dashboard-visible comments table,
    which is how a Gemini key leaked once (TMDEV-46). No message leaving this
    module may contain the token.
  * **The limits.** Discord answers 400 when an embed exceeds any of its size
    caps, and a rejected message is a notification the human simply never gets,
    with nothing downstream reporting it. Composition has to clip on the way in.
  * **The tri-state probe.** Only a positive rejection may gate a settings save.
    A timeout or a 5xx must read as "unknown", never "invalid".

Run from renderer/api/: pytest tests/test_discord_notify.py
"""
import logging
import os

import httpx
import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import discord_notify as dn

_RealHttpxClient = httpx.Client

TOKEN = "abcdefghij0123456789_KLMNOPqrstuvwxyz-ABCDE"
URL = f"https://discord.com/api/webhooks/123456789012345678/{TOKEN}"


def _factory(handler):
    def _make(*args, **kwargs):
        kwargs.pop("timeout", None)
        return _RealHttpxClient(transport=httpx.MockTransport(handler), **kwargs)
    return _make


def _record(monkeypatch, responder):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responder(request)

    monkeypatch.setattr(dn.httpx, "Client", _factory(handler))
    return seen


# ── URL shape ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url", [
    URL,
    f"https://discordapp.com/api/webhooks/123456789012345678/{TOKEN}",
    f"https://ptb.discord.com/api/webhooks/123456789012345678/{TOKEN}",
    f"https://canary.discord.com/api/v10/webhooks/123456789012345678/{TOKEN}",
    f"https://discord.com/api/webhooks/123456789012345678/{TOKEN}/",
])
def test_every_form_discord_hands_out_is_accepted(url):
    """The copy button produces several of these depending on client and
    channel — rejecting one would look like a broken feature."""
    webhook_id, token = dn.parse_webhook_url(url)
    assert webhook_id == "123456789012345678"
    assert token == TOKEN


@pytest.mark.parametrize("url", [
    "",
    "not a url",
    "https://example.com/api/webhooks/123456789012345678/" + TOKEN,
    "http://discord.com/api/webhooks/123456789012345678/" + TOKEN,  # plain http
    "https://discord.com/api/webhooks/123456789012345678",          # no token
    "https://discord.com/api/webhooks/abc/" + TOKEN,                # non-numeric id
    "https://discord.com/api/webhooks/123456789012345678/short",
])
def test_anything_else_is_rejected(url):
    with pytest.raises(ValueError):
        dn.parse_webhook_url(url)


def test_the_error_names_where_to_find_the_url():
    """A shape error is shown verbatim in the dashboard, so it has to be
    actionable rather than a regex dump."""
    with pytest.raises(ValueError, match="Integrations"):
        dn.parse_webhook_url("nope")


# ── Redaction ────────────────────────────────────────────────────────────────

def test_redact_removes_the_token_but_keeps_the_webhook_identifiable():
    out = dn.redact(f"failed posting to {URL}", URL)
    assert TOKEN not in out
    assert "123456789012345678" in out


def test_redact_drops_a_malformed_url_wholesale():
    """If the token cannot be isolated, nothing of the value survives — a
    half-redacted secret is not a redacted secret."""
    weird = "https://discord.com/api/webhooks/oops"
    out = dn.redact(f"boom {weird}", weird)
    assert "oops" not in out


def test_a_transport_failure_never_carries_the_token(monkeypatch):
    def boom(request):
        raise httpx.ConnectError("failed to connect", request=request)

    _record(monkeypatch, boom)
    with pytest.raises(dn.DiscordError) as excinfo:
        dn.send(URL, {"content": "hi"})
    assert TOKEN not in str(excinfo.value)


def test_an_http_error_never_carries_the_token(monkeypatch):
    _record(monkeypatch, lambda r: httpx.Response(
        400, json={"message": f"bad request for {URL}"}, request=r))
    with pytest.raises(dn.DiscordError) as excinfo:
        dn.send(URL, {"content": "hi"})
    assert TOKEN not in str(excinfo.value)


def test_httpx_own_request_log_cannot_print_the_token(caplog):
    """httpx logs "HTTP Request: <method> <url>" at INFO on every call, and a
    Discord webhook token lives in the URL by construction — so that line prints
    a live credential unless something rewrites it.

    Found live, not by inspection: a real working token reached both
    `docker logs` and a JSONL log file this way. Value-based redaction cannot
    close it, because POST /settings probes the URL *before* storing it.
    """
    log = logging.getLogger("httpx")
    with caplog.at_level(logging.INFO, logger="httpx"):
        log.info('HTTP Request: GET %s "HTTP/1.1 200 OK"', URL)
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert TOKEN not in text
    assert "123456789012345678" in text, "the webhook should stay identifiable"


def test_the_filter_leaves_other_httpx_lines_alone():
    """It must not become a blanket suppression of httpx logging — those lines
    are how Gemini and postforme calls get debugged."""
    record = logging.LogRecord("httpx", logging.INFO, __file__, 1,
                              'HTTP Request: GET %s "HTTP/1.1 200 OK"',
                              ("https://api.postforme.dev/v1/social-accounts",), None)
    dn._RedactWebhookUrls().filter(record)
    assert "api.postforme.dev/v1/social-accounts" in record.getMessage()


def test_a_real_request_does_not_log_the_token(monkeypatch, caplog):
    """End to end through send(), rather than a hand-built log line."""
    _record(monkeypatch, lambda r: httpx.Response(404, json={"message": "Unknown Webhook"},
                                                  request=r))
    with caplog.at_level(logging.DEBUG):
        with pytest.raises(dn.DiscordError):
            dn.send(URL, {"content": "x"})
    assert TOKEN not in "\n".join(r.getMessage() for r in caplog.records)


# ── verify_webhook: the tri-state ────────────────────────────────────────────

def test_a_live_webhook_is_valid_and_names_its_channel(monkeypatch):
    seen = _record(monkeypatch, lambda r: httpx.Response(
        200, json={"name": "tubematic", "channel_id": "42"}, request=r))
    verdict, detail = dn.verify_webhook(URL)
    assert verdict == "valid"
    assert "tubematic" in detail and "42" in detail
    assert seen[0].method == "GET", "the probe must never post a message"


@pytest.mark.parametrize("status,message", [
    (404, "Unknown Webhook"),
    (401, "Invalid Webhook Token"),
])
def test_a_deleted_or_mistyped_webhook_is_invalid(monkeypatch, status, message):
    _record(monkeypatch, lambda r: httpx.Response(
        status, json={"message": message}, request=r))
    verdict, detail = dn.verify_webhook(URL)
    assert verdict == "invalid"
    assert message in detail


@pytest.mark.parametrize("responder", [
    lambda r: httpx.Response(500, text="oops", request=r),
    lambda r: httpx.Response(429, json={"retry_after": 1}, request=r),
])
def test_discord_having_a_bad_day_is_unknown_not_invalid(monkeypatch, responder):
    """Only a positive rejection may gate a settings save — otherwise Settings
    becomes un-saveable whenever Discord is unwell."""
    _record(monkeypatch, responder)
    assert dn.verify_webhook(URL)[0] == "unknown"


def test_an_unreachable_discord_is_unknown(monkeypatch):
    def boom(request):
        raise httpx.ConnectTimeout("timed out", request=request)

    _record(monkeypatch, boom)
    verdict, detail = dn.verify_webhook(URL)
    assert verdict == "unknown"
    assert TOKEN not in detail


def test_a_malformed_url_is_invalid_without_any_request(monkeypatch):
    seen = _record(monkeypatch, lambda r: httpx.Response(200, json={}, request=r))
    assert dn.verify_webhook("nonsense")[0] == "invalid"
    assert seen == []


# ── send ─────────────────────────────────────────────────────────────────────

def test_a_successful_send_posts_the_payload_to_the_webhook(monkeypatch):
    seen = _record(monkeypatch, lambda r: httpx.Response(204, request=r))
    dn.send(URL, {"embeds": [{"title": "hi"}]})
    assert len(seen) == 1
    assert seen[0].method == "POST"
    assert str(seen[0].url) == URL


def test_204_with_no_body_is_success_not_an_error(monkeypatch):
    """Execute-webhook answers 204 with nothing in it unless ?wait=true, which
    we deliberately do not pass."""
    _record(monkeypatch, lambda r: httpx.Response(204, request=r))
    dn.send(URL, {"content": "x"})  # must not raise


def test_a_rate_limit_is_retried_once_then_succeeds(monkeypatch):
    monkeypatch.setattr(dn.time, "sleep", lambda _s: None)
    calls = []

    def responder(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, json={"retry_after": 0.2}, request=request)
        return httpx.Response(204, request=request)

    _record(monkeypatch, responder)
    dn.send(URL, {"content": "x"})
    assert len(calls) == 2


def test_a_second_rate_limit_gives_up_rather_than_looping(monkeypatch):
    """This runs inline in the render worker's tick — retrying forever would
    stall rendering. The sweep's marker stays unadvanced, so the next tick
    retries anyway."""
    monkeypatch.setattr(dn.time, "sleep", lambda _s: None)
    calls = []

    def responder(request):
        calls.append(request)
        return httpx.Response(429, json={"retry_after": 0.2}, request=request)

    _record(monkeypatch, responder)
    with pytest.raises(dn.DiscordError):
        dn.send(URL, {"content": "x"})
    assert len(calls) == 2


def test_an_absurd_retry_after_is_clamped(monkeypatch):
    slept = []
    monkeypatch.setattr(dn.time, "sleep", slept.append)
    calls = []

    def responder(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(429, json={"retry_after": 9999}, request=request)
        return httpx.Response(204, request=request)

    _record(monkeypatch, responder)
    dn.send(URL, {"content": "x"})
    assert slept == [5.0]


def test_send_refuses_a_non_webhook_url_before_any_request(monkeypatch):
    seen = _record(monkeypatch, lambda r: httpx.Response(204, request=r))
    with pytest.raises(ValueError):
        dn.send("https://example.com/hook", {"content": "x"})
    assert seen == []


# ── Composition: the Discord limits ──────────────────────────────────────────

def _video(**over):
    base = {
        "id": "vid_abc", "title": "DNS in 90 seconds", "topic": "How DNS resolution works",
        "strategy": "curriculum", "producibility_score": 8, "project_name": "Networking",
        "script": "one two three four five", "video_version": 2,
    }
    base.update(over)
    return base


def _assert_within_discord_limits(payload):
    embeds = payload["embeds"]
    assert len(embeds) <= dn.MAX_EMBEDS
    for embed in embeds:
        assert len(embed.get("title", "")) <= dn.MAX_TITLE
        assert len(embed.get("description", "")) <= dn.MAX_DESCRIPTION
        assert len(embed.get("fields", [])) <= dn.MAX_FIELDS_PER_EMBED
        for field in embed.get("fields", []):
            assert 0 < len(field["name"]) <= dn.MAX_FIELD_NAME
            assert 0 < len(field["value"]) <= dn.MAX_FIELD_VALUE
    assert dn._total_chars(embeds) <= dn.MAX_TOTAL_CHARS


@pytest.mark.parametrize("build,arg", [
    (dn.build_topics_payload, [_video()]),
    (dn.build_script_ready_payload, _video()),
    (dn.build_video_ready_payload, _video()),
    (dn.build_voicing_stalled_payload, _video(stalled_secs=5460)),
])
def test_every_builder_stays_within_the_limits(build, arg):
    _assert_within_discord_limits(build(arg))


@pytest.mark.parametrize("build,arg", [
    (dn.build_topics_payload, [_video(title="T" * 900, topic="x" * 9000)] * 40),
    (dn.build_script_ready_payload, _video(title="T" * 900, script="word " * 4000)),
    (dn.build_video_ready_payload,
     _video(title="T" * 900, review_summary="r" * 9000, duration_secs=132)),
    (dn.build_voicing_stalled_payload, _video(title="T" * 900, stalled_secs=10 ** 9)),
])
def test_absurd_input_still_stays_within_the_limits(build, arg):
    """A 400 from Discord loses the notification silently, so nothing the
    pipeline can produce may exceed a cap."""
    _assert_within_discord_limits(build(arg))


def test_enforce_limits_trims_until_it_fits():
    """Direct test of the backstop: the per-item budgets normally keep messages
    well inside 6000, so nothing else would exercise the trimming loop."""
    embed = {"title": "t", "fields": [{"name": "n" * 200, "value": "v" * 1000}
                                      for _ in range(25)]}
    out = dn._enforce_limits([embed])
    assert dn._total_chars(out) <= dn.MAX_TOTAL_CHARS
    assert len(out[0]["fields"]) < 25


# ── Composition: content ─────────────────────────────────────────────────────

def test_topics_are_bundled_into_one_message():
    payload = dn.build_topics_payload([_video(id=f"v{i}") for i in range(6)])
    assert len(payload["embeds"]) == 1
    assert len(payload["embeds"][0]["fields"]) == 6
    assert "6 new topics" in payload["embeds"][0]["title"]


def test_one_topic_reads_as_singular():
    assert "1 new topic proposed" in dn.build_topics_payload([_video()])["embeds"][0]["title"]


def test_topics_beyond_the_cap_are_counted_not_dropped_silently():
    payload = dn.build_topics_payload([_video(id=f"v{i}") for i in range(dn.TOPICS_PER_MESSAGE + 4)])
    embed = payload["embeds"][0]
    assert len(embed["fields"]) == dn.TOPICS_PER_MESSAGE
    assert "4 more" in embed["description"]


def test_a_topic_without_a_title_falls_back_to_its_brief():
    """title is NOT NULL DEFAULT '' and every row predating the short-title
    split holds '' — a nullish check here would blank every legacy card."""
    field = dn.build_topics_payload([_video(title="")])["embeds"][0]["fields"][0]
    assert "How DNS resolution works" in field["name"]


def test_a_topic_with_neither_title_nor_brief_still_names_something():
    field = dn.build_topics_payload([_video(title="", topic="")])["embeds"][0]["fields"][0]
    assert field["name"] == "vid_abc"


def test_script_ready_says_that_approving_costs_money():
    """This is the checkpoint where ElevenLabs charges per character and the
    charge is not refundable — the message has to say so."""
    payload = dn.build_script_ready_payload(_video())
    assert "ElevenLabs" in payload["embeds"][0]["description"]


def test_script_ready_reports_word_count_and_estimated_runtime():
    payload = dn.build_script_ready_payload(_video(script=" ".join(["word"] * 314)))
    length = next(f for f in payload["embeds"][0]["fields"] if f["name"] == "Length")
    assert "314 words" in length["value"]
    # 314 words at the measured ~157 wpm is two minutes.
    assert "2m 00s" in length["value"]


def test_video_ready_carries_duration_version_and_the_review_verdict():
    payload = dn.build_video_ready_payload(
        _video(duration_secs=132, review_summary="No blocking defects found."))
    fields = {f["name"]: f["value"] for f in payload["embeds"][0]["fields"]}
    assert fields["Duration"] == "2m 12s"
    assert fields["Version"] == "v2"
    assert "No blocking defects" in fields["AI review"]


def test_video_ready_omits_duration_when_the_timeline_could_not_be_read():
    payload = dn.build_video_ready_payload(_video(duration_secs=None))
    assert "Duration" not in {f["name"] for f in payload["embeds"][0]["fields"]}


def test_voicing_stalled_names_the_video_and_how_long():
    embed = dn.build_voicing_stalled_payload(_video(stalled_secs=5460))["embeds"][0]
    assert "DNS in 90 seconds" in embed["title"]
    assert "1h 31m" in embed["description"]
    assert embed["color"] == dn.COLOR_ALERT
    assert "vid_abc" in embed["footer"]["text"]


# ── Composition: links ───────────────────────────────────────────────────────

@pytest.mark.parametrize("build,arg,path", [
    (dn.build_topics_payload, [_video()], "/topics"),
    (dn.build_script_ready_payload, _video(), "/"),
    (dn.build_video_ready_payload, _video(), "/library"),
    (dn.build_voicing_stalled_payload, _video(stalled_secs=5460), "/"),
])
def test_a_configured_base_url_becomes_a_link(build, arg, path):
    desc = build(arg, base_url="http://box:3000")["embeds"][0]["description"]
    assert f"http://box:3000{path}" in desc


def test_a_trailing_slash_on_the_base_url_does_not_double_up():
    desc = dn.build_topics_payload([_video()], base_url="http://box:3000/")["embeds"][0]["description"]
    assert "3000//" not in desc


@pytest.mark.parametrize("build,arg", [
    (dn.build_topics_payload, [_video()]),
    (dn.build_script_ready_payload, _video()),
    (dn.build_video_ready_payload, _video()),
    (dn.build_voicing_stalled_payload, _video(stalled_secs=5460)),
])
def test_no_base_url_means_no_link_rather_than_a_broken_one(build, arg):
    """The container has no idea what hostname a human reaches it by, so there
    is no default to guess."""
    embed = build(arg)["embeds"][0]
    assert "http" not in embed.get("description", "")


def test_a_topic_shows_its_score_out_of_ten():
    field = dn.build_topics_payload([_video(producibility_score=8)])["embeds"][0]["fields"][0]
    assert "score 8/10" in field["value"]


def test_an_unscored_topic_says_so_rather_than_scoring_zero():
    """A New Video submission left at TOPIC_PROPOSED is stored with score 0,
    which means unscored; "0/10" would read as a topic that failed the rubric."""
    field = dn.build_topics_payload(
        [_video(strategy="manual", producibility_score=0)])["embeds"][0]["fields"][0]
    assert "unscored" in field["value"]
    assert "0/10" not in field["value"]
