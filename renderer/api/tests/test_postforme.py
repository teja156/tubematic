"""Wire-level tests for postforme.py (TMDEV-83).

Modelled on test_ai_review.py rather than test_pipeline.py: httpx.MockTransport
means real httpx.Request objects reach the assertions, so method, path, headers
and query string are genuinely exercised. That is what catches an API key
leaking into a URL, which is the failure mode that actually happened once
(TMDEV-46).

Two things here are load-bearing and were established by probing the live API,
not read off the swagger:

  * Credential scrubbing. POST /social-posts nests the whole target account in
    its response, including a live OAuth access_token and a NON-EXPIRING
    refresh_token. Every response this module returns must already be scrubbed
    — not scrubbed later at a display boundary, because the publish path
    persists errors and comments.
  * 201, not 200. Both create-upload-url and social-posts answer 201 while the
    swagger documents 200. A client checking `== 200` breaks on the happy path.

Run from renderer/api/: pytest tests/test_postforme.py
"""
import json
import os
from pathlib import Path

import httpx
import pytest

os.environ.setdefault("TUBEMATIC_DB", ":memory:")

import postforme

# Captured before any monkeypatching, for the same reason as test_ai_review.py:
# the factory must build real Clients with a MockTransport, not recurse.
_RealHttpxClient = httpx.Client

FIXTURES = Path(__file__).parent / "fixtures"

KEY = "pfm-test-key-abc123"

# A response shaped like the real one probed on 2026-09-05 — the account object
# is nested inside the post, which is what makes the write path dangerous.
POST_RESPONSE = {
    "id": "sp_abc",
    "external_id": "vid_123",
    "status": "scheduled",
    "social_accounts": [{
        "id": "spc_yt",
        "platform": "youtube",
        "username": "Chan",
        "access_token": "ya29.REAL-LIVE-TOKEN",
        "refresh_token": "1//REAL-REFRESH-TOKEN",
    }],
}


def _factory(handler):
    def _make(*args, **kwargs):
        kwargs.pop("timeout", None)
        return _RealHttpxClient(transport=httpx.MockTransport(handler), **kwargs)
    return _make


def _record(monkeypatch, responder):
    """Swap httpx.Client for a MockTransport-backed one; return the request log."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responder(request)

    monkeypatch.setattr(postforme.httpx, "Client", _factory(handler))
    return seen


def _ok(request, body, status=200):
    return httpx.Response(status, json=body, request=request)


@pytest.fixture(autouse=True)
def _clear_rate_limiter():
    """The limiter's window is module state, so without this the suite starts
    sleeping on itself once tests run faster than 5/second — which they do."""
    postforme._recent_calls.clear()
    yield
    postforme._recent_calls.clear()


# ── scrubbing ────────────────────────────────────────────────────────────────

def test_scrub_strips_credentials_at_the_top_level():
    assert postforme.scrub({"id": "x", "access_token": "t", "refresh_token": "r"}) == {
        "id": "x", "access_token": "<redacted>", "refresh_token": "<redacted>",
    }


def test_scrub_reaches_credentials_nested_inside_lists_and_dicts():
    """The real shape: the token sits two levels down, inside a list."""
    out = postforme.scrub(POST_RESPONSE)
    acct = out["social_accounts"][0]
    assert acct["access_token"] == "<redacted>"
    assert acct["refresh_token"] == "<redacted>"
    assert acct["username"] == "Chan"


def test_scrub_leaves_absent_and_empty_credentials_alone():
    """A null token is not a secret; replacing it would invent one."""
    assert postforme.scrub({"access_token": None})["access_token"] is None
    assert postforme.scrub({"access_token": ""})["access_token"] == ""


def test_scrub_does_not_mutate_its_input():
    src = {"social_accounts": [{"access_token": "t"}]}
    postforme.scrub(src)
    assert src["social_accounts"][0]["access_token"] == "t"


# ── request shape ────────────────────────────────────────────────────────────

def test_the_key_travels_as_a_header_and_never_in_the_url(monkeypatch):
    seen = _record(monkeypatch, lambda r: _ok(r, {"data": []}))
    postforme.list_accounts(KEY)
    req = seen[0]
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    assert KEY not in str(req.url)


def test_list_accounts_returns_the_data_list_scrubbed(monkeypatch):
    body = {"data": [{"id": "spc_yt", "platform": "youtube", "username": "Chan",
                      "access_token": "ya29.LIVE", "refresh_token": "1//LIVE"}]}
    _record(monkeypatch, lambda r: _ok(r, body))
    accounts = postforme.list_accounts(KEY)
    assert accounts[0]["access_token"] == "<redacted>"
    assert accounts[0]["username"] == "Chan"


AUTH_URL_RESPONSE = {
    "platform": "instagram",
    "url": "https://www.instagram.com/oauth/authorize?client_id=1&state=abc"
           "&scope=instagram_business_basic,instagram_business_content_publish,"
           "instagram_business_manage_insights",
}


def test_create_auth_url_posts_the_platform_and_permissions(monkeypatch):
    """Probed live: the scopes in the minted URL follow `permissions`, and
    postforme's default when it is absent is posts alone."""
    seen = _record(monkeypatch, lambda r: _ok(r, AUTH_URL_RESPONSE, 201))
    out = postforme.create_auth_url(KEY, platform="instagram",
                                    permissions=["posts", "feeds"])
    req = seen[0]
    assert req.method == "POST"
    assert req.url.path.endswith("/social-accounts/auth-url")
    assert json.loads(req.content) == {"platform": "instagram",
                                       "permissions": ["posts", "feeds"]}
    assert req.headers["Authorization"] == f"Bearer {KEY}"
    assert KEY not in str(req.url)
    assert out == AUTH_URL_RESPONSE


def test_connect_permissions_always_include_feeds():
    """The reason the connect route exists: without feeds an account publishes
    and silently never reports a metric."""
    assert set(postforme.CONNECT_PERMISSIONS) == {"posts", "feeds"}


def test_a_disabled_platform_surfaces_postformes_own_message(monkeypatch):
    """Probed live 2026-10-10: the body is a top-level `message`, not
    `error.message`. It is actionable ("enable it in Project Setup"), so it must
    reach the user as text, not as a JSON dump."""
    msg = ("Social provider app credentials not found for facebook. "
           "Please set up or enable this platform in Project Setup.")
    _record(monkeypatch, lambda r: _ok(r, {"statusCode": 404, "message": msg}, 404))
    with pytest.raises(postforme.PostformeError) as exc:
        postforme.create_auth_url(KEY, platform="facebook", permissions=["posts", "feeds"])
    assert exc.value.status_code == 404
    assert str(exc.value) == f"postforme returned HTTP 404: {msg}"


def test_a_nested_error_message_still_wins_over_a_top_level_one(monkeypatch):
    _record(monkeypatch, lambda r: _ok(
        r, {"error": {"message": "nested"}, "message": "top"}, 400))
    with pytest.raises(postforme.PostformeError) as exc:
        postforme.list_accounts(KEY)
    assert str(exc.value) == "postforme returned HTTP 400: nested"


def test_a_top_level_message_is_redacted_too(monkeypatch):
    _record(monkeypatch, lambda r: _ok(r, {"message": f"bad key {KEY}"}, 401))
    with pytest.raises(postforme.PostformeError) as exc:
        postforme.list_accounts(KEY)
    assert KEY not in str(exc.value)


def test_create_upload_url_accepts_201(monkeypatch):
    """Probed live: this endpoint answers 201, though the swagger says 200."""
    _record(monkeypatch, lambda r: _ok(r, {"upload_url": "https://u", "media_url": "https://m"}, 201))
    assert postforme.create_upload_url(KEY) == {"upload_url": "https://u", "media_url": "https://m"}


def test_create_post_accepts_201_and_scrubs_the_nested_account(monkeypatch):
    seen = _record(monkeypatch, lambda r: _ok(r, POST_RESPONSE, 201))
    out = postforme.create_post(
        KEY, caption="hi", social_account_ids=["spc_yt"], media_url="https://m",
        platform_configurations={"youtube": {"title": "T"}}, external_id="vid_123",
    )
    assert out["id"] == "sp_abc"
    assert out["social_accounts"][0]["access_token"] == "<redacted>"

    body = json.loads(seen[0].content)
    assert body["social_accounts"] == ["spc_yt"]
    assert body["media"] == [{"url": "https://m"}]
    assert body["external_id"] == "vid_123"


def test_create_post_omits_scheduled_at_so_the_post_goes_out_now(monkeypatch):
    """scheduled_at is nullable and absent means publish immediately — so a
    publish-now must not send it at all, not even as null or as "now"."""
    seen = _record(monkeypatch, lambda r: _ok(r, POST_RESPONSE, 201))
    postforme.create_post(KEY, caption="hi", social_account_ids=["a"], media_url="https://m",
                          platform_configurations={}, external_id="vid_1")
    assert "scheduled_at" not in json.loads(seen[0].content)


def test_create_post_sends_a_schedule_when_given(monkeypatch):
    seen = _record(monkeypatch, lambda r: _ok(r, POST_RESPONSE, 201))
    postforme.create_post(KEY, caption="hi", social_account_ids=["a"], media_url="https://m",
                          platform_configurations={}, external_id="vid_1",
                          scheduled_at="2026-10-01T03:30:00Z")
    assert json.loads(seen[0].content)["scheduled_at"] == "2026-10-01T03:30:00Z"


def test_delete_post_deletes_by_id(monkeypatch):
    seen = _record(monkeypatch, lambda r: _ok(r, {"success": True}))
    postforme.delete_post(KEY, post_id="sp_abc")
    assert seen[0].method == "DELETE"
    assert seen[0].url.path.endswith("/social-posts/sp_abc")


def test_delete_post_treats_success_false_as_a_failure(monkeypatch):
    """postforme answers 200 {success:false} when its own DB delete fails — the
    post is still scheduled, so reading the status alone would report a cancel
    that did not happen."""
    _record(monkeypatch, lambda r: _ok(r, {"success": False}))
    with pytest.raises(postforme.PostformeError):
        postforme.delete_post(KEY, post_id="sp_abc")


def test_delete_post_carries_the_status_of_a_refusal(monkeypatch):
    """The caller tells "already going out" (400) from "not found" (404)."""
    _record(monkeypatch, lambda r: _ok(
        r, {"message": "Can only delete scheduled or draft posts"}, 400))
    with pytest.raises(postforme.PostformeError) as exc:
        postforme.delete_post(KEY, post_id="sp_abc")
    assert exc.value.status_code == 400


def test_get_post_results_filters_by_post_id(monkeypatch):
    seen = _record(monkeypatch, lambda r: _ok(r, {"data": []}))
    postforme.get_post_results(KEY, post_id="sp_abc")
    assert seen[0].url.params["post_id"] == "sp_abc"


def test_get_account_feed_asks_for_metrics_and_filters_to_one_post(monkeypatch):
    """The whole reason analytics is cheap: the feed filters server-side, so we
    never page through an account's unrelated posts."""
    seen = _record(monkeypatch, lambda r: _ok(r, {"data": [], "meta": {}}))
    postforme.get_account_feed(KEY, social_account_id="spc_yt", social_post_id="sp_abc")
    assert "/social-account-feeds/spc_yt" in seen[0].url.path
    assert seen[0].url.params["expand"] == "metrics"
    assert seen[0].url.params["social_post_id"] == "sp_abc"


def test_upload_media_puts_the_bytes_without_an_authorization_header(monkeypatch, tmp_path):
    """upload_url is pre-signed. Sending the API key to a storage host would
    hand it to a third party for no reason."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(postforme.httpx, "Client", _factory(handler))
    mp4 = tmp_path / "v.mp4"
    mp4.write_bytes(b"\x00\x01binary")
    postforme.upload_media("https://storage.example/signed", str(mp4))

    assert seen[0].method == "PUT"
    assert seen[0].content == b"\x00\x01binary"
    assert seen[0].headers["Content-Type"] == "video/mp4"
    assert "Authorization" not in seen[0].headers


# ── errors ───────────────────────────────────────────────────────────────────

def test_an_http_error_raises_with_the_key_redacted(monkeypatch):
    _record(monkeypatch, lambda r: _ok(r, {"error": {"message": f"bad key {KEY}"}}, 401))
    with pytest.raises(postforme.PostformeError) as exc:
        postforme.list_accounts(KEY)
    assert KEY not in str(exc.value)
    assert exc.value.status_code == 401


def test_an_error_body_carrying_a_credential_is_scrubbed_too(monkeypatch):
    """Errors are persisted to video_publications.error and to comments."""
    _record(monkeypatch, lambda r: _ok(r, {"error": {"message": "no"},
                                          "account": {"refresh_token": "1//LIVE"}}, 400))
    with pytest.raises(postforme.PostformeError) as exc:
        postforme.list_accounts(KEY)
    assert "1//LIVE" not in str(exc.value)


def test_a_transport_failure_raises_postforme_error_not_httpx(monkeypatch):
    """Callers catch one exception type; an httpx error escaping would be a 500."""
    def boom(request):
        raise httpx.ConnectError("unreachable", request=request)

    monkeypatch.setattr(postforme.httpx, "Client", _factory(boom))
    with pytest.raises(postforme.PostformeError):
        postforme.list_accounts(KEY)


# ── platform configuration builder ───────────────────────────────────────────

def test_youtube_gets_title_and_description_as_separate_fields():
    cfg = postforme.build_platform_configurations(["youtube"], "My Title", "The body.")
    assert cfg["youtube"]["title"] == "My Title"
    assert cfg["youtube"]["description"] == "The body."
    assert "caption" not in cfg["youtube"]


def test_caption_only_platforms_get_title_and_description_composed():
    """Instagram/Facebook have no title field. A bare title there produces a
    worse post than no post at all."""
    cfg = postforme.build_platform_configurations(["instagram", "facebook"], "My Title", "The body.")
    for platform in ("instagram", "facebook"):
        assert cfg[platform]["caption"] == "My Title\n\nThe body."
        assert "title" not in cfg[platform]


def test_tiktok_gets_both_a_title_and_a_composed_caption():
    """TikTok has a title field too — the ticket's two-row mapping table missed
    this, and the swagger confirms TiktokConfigurationDto.title exists."""
    cfg = postforme.build_platform_configurations(["tiktok"], "My Title", "The body.")
    assert cfg["tiktok"]["title"] == "My Title"
    assert cfg["tiktok"]["caption"] == "My Title\n\nThe body."


def test_ai_disclosure_is_always_set_on_the_platforms_that_have_a_flag():
    """Tubematic output is AI-generated and TikTok requires the disclosure.
    Hardcoded true by decision — deliberately not a setting."""
    cfg = postforme.build_platform_configurations(["youtube", "tiktok"], "T", "D")
    assert cfg["youtube"]["contains_synthetic_media"] is True
    assert cfg["tiktok"]["is_ai_generated"] is True


def test_an_empty_description_does_not_leave_trailing_blank_lines():
    cfg = postforme.build_platform_configurations(["instagram"], "Just a title", "")
    assert cfg["instagram"]["caption"] == "Just a title"


def test_an_unknown_platform_is_skipped_rather_than_sent_blind():
    """postforme silently accepts anything, so an unmapped platform would post
    with no per-platform content and no error. Better to omit the override."""
    cfg = postforme.build_platform_configurations(["youtube", "pinterest"], "T", "D")
    assert set(cfg) == {"youtube"}


def test_every_field_the_builder_emits_exists_in_the_live_swagger_schema():
    """The load-bearing test for this module.

    Probed live: postforme SILENTLY ACCEPTS unknown keys inside
    platform_configurations — a bogus field returned 201 and was stored
    verbatim. So a typo'd `contains_synthetic_media` would mean the AI
    disclosure is never set, with nothing anywhere reporting a problem. There
    is no server-side safety net; this fixture is the only one.

    Fixture generated from https://api.postforme.dev/swagger/swagger-ui-init.js
    on 2026-09-05.
    """
    valid = json.loads((FIXTURES / "postforme_platform_fields.json").read_text())
    cfg = postforme.build_platform_configurations(
        ["youtube", "tiktok", "instagram", "facebook"], "T", "D")
    for platform, fields in cfg.items():
        unknown = set(fields) - set(valid[platform])
        assert not unknown, f"{platform} would send fields postforme does not define: {unknown}"


def test_the_create_post_body_uses_only_documented_top_level_fields(monkeypatch):
    valid = json.loads((FIXTURES / "postforme_platform_fields.json").read_text())
    seen = _record(monkeypatch, lambda r: _ok(r, POST_RESPONSE, 201))
    postforme.create_post(KEY, caption="c", social_account_ids=["a"], media_url="https://m",
                          platform_configurations={}, external_id="vid_1")
    unknown = set(json.loads(seen[0].content)) - set(valid["_create_social_post"])
    assert not unknown, f"undocumented top-level fields: {unknown}"


# ── metrics adapter ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("platform,raw,expected", [
    ("youtube",
     {"views": 10, "likes": 2, "comments": 1, "shares": 3},
     {"views": 10, "likes": 2, "comments": 1, "shares": 3}),
    ("tiktok",
     {"view_count": 10, "like_count": 2, "comment_count": 1, "share_count": 3},
     {"views": 10, "likes": 2, "comments": 1, "shares": 3}),
    ("instagram",
     {"views": 10, "likes": 2, "comments": 1, "shares": 3},
     {"views": 10, "likes": 2, "comments": 1, "shares": 3}),
])
def test_the_three_well_behaved_platforms_map_straight_through(platform, raw, expected):
    assert postforme.extract_metrics(platform, raw) == expected


def test_facebook_needs_a_real_adapter_because_it_names_nothing_the_same_way():
    """Facebook has no `likes` and no `views`: reactions_total and video_views
    are the nearest equivalents. This is why raw_json is stored alongside."""
    out = postforme.extract_metrics("facebook", {
        "reactions_total": 7, "video_views": 99, "media_views": 120,
        "comments": 4, "shares": 5,
    })
    assert out == {"views": 99, "likes": 7, "comments": 4, "shares": 5}


def test_facebook_falls_back_to_media_views_when_there_is_no_video_view_count():
    out = postforme.extract_metrics("facebook", {"media_views": 120})
    assert out["views"] == 120


def test_a_missing_metric_is_none_not_zero():
    """NULL and 0 are different claims: one is "not reported", the other is
    "reported as none". A chart that reads 0 as a real datapoint lies."""
    assert postforme.extract_metrics("youtube", {"views": 5}) == {
        "views": 5, "likes": None, "comments": None, "shares": None,
    }


def test_an_unknown_platform_yields_all_nones_rather_than_raising():
    """A new platform appearing upstream must not break the metrics poll for
    every other publication in the same pass."""
    assert postforme.extract_metrics("mastodon", {"views": 1}) == {
        "views": None, "likes": None, "comments": None, "shares": None,
    }


def test_metrics_missing_entirely_is_handled():
    assert postforme.extract_metrics("youtube", None)["views"] is None


def test_instagram_and_facebook_post_to_reels_not_the_feed():
    """Every render is 1080x1920. Leaving placement to postforme's default puts
    a 9:16 video on the feed — letterboxed, and off the surface short-form
    video is actually watched on."""
    cfg = postforme.build_platform_configurations(["instagram", "facebook"], "T", "D")
    assert cfg["instagram"]["placement"] == "reels"
    assert cfg["facebook"]["placement"] == "reels"


def test_youtube_gets_no_placement_because_no_such_field_exists():
    """Not an oversight. YoutubeConfigurationDto has no placement and no Shorts
    flag, because the YouTube Data API has none either — YouTube infers Shorts
    from the file (vertical aspect AND <= 3 minutes). Sending an invented field
    would be silently accepted and silently ignored."""
    cfg = postforme.build_platform_configurations(["youtube"], "T", "D")
    assert "placement" not in cfg["youtube"]


# ── privacy ─────────────────────────────────────────────────────────────────
#
# Deliberately per-platform rather than one shared setting: YouTube has three
# options, TikTok two, and Instagram/Facebook none at all. A single control
# would either offer "unlisted" where it cannot exist or silently map it onto
# something the user did not choose.

def test_privacy_options_match_what_each_platform_actually_supports():
    assert postforme.PRIVACY_OPTIONS["youtube"] == ("public", "unlisted", "private")
    assert postforme.PRIVACY_OPTIONS["tiktok"] == ("public", "private")
    # Not a gap: neither DTO has the field, because neither platform has the
    # concept — a Reel is public or it is not posted.
    assert "instagram" not in postforme.PRIVACY_OPTIONS
    assert "facebook" not in postforme.PRIVACY_OPTIONS


def test_privacy_defaults_to_public_matching_the_platforms_own_default():
    """postforme documents `default: public` on both fields. Sending it
    explicitly rather than omitting it keeps what we ask for visible in the
    request instead of resting on someone else's default."""
    cfg = postforme.build_platform_configurations(["youtube", "tiktok"], "T", "D")
    assert cfg["youtube"]["privacy_status"] == "public"
    assert cfg["tiktok"]["privacy_status"] == "public"


def test_each_platform_takes_its_own_privacy_choice():
    cfg = postforme.build_platform_configurations(
        ["youtube", "tiktok"], "T", "D", privacy={"youtube": "unlisted", "tiktok": "private"})
    assert cfg["youtube"]["privacy_status"] == "unlisted"
    assert cfg["tiktok"]["privacy_status"] == "private"


def test_a_value_a_platform_cannot_honour_is_rejected_not_quietly_downgraded():
    """postforme silently accepts anything it is given, so an unsupported value
    would be stored and then ignored — the post would just be public with
    nothing reporting why. Better to refuse it here."""
    with pytest.raises(ValueError) as exc:
        postforme.build_platform_configurations(
            ["tiktok"], "T", "D", privacy={"tiktok": "unlisted"})
    assert "tiktok" in str(exc.value)


def test_privacy_for_a_platform_that_has_no_such_setting_is_ignored():
    """The UI never offers it, but a hand-made request must not invent a field
    on a DTO that has none."""
    cfg = postforme.build_platform_configurations(
        ["instagram"], "T", "D", privacy={"instagram": "private"})
    assert "privacy_status" not in cfg["instagram"]


def test_privacy_values_stay_inside_the_swagger_field_set():
    valid = json.loads((FIXTURES / "postforme_platform_fields.json").read_text())
    cfg = postforme.build_platform_configurations(
        ["youtube", "tiktok", "instagram", "facebook"], "T", "D",
        privacy={"youtube": "private", "tiktok": "private"})
    for platform, fields in cfg.items():
        assert not set(fields) - set(valid[platform])


# ── rate limiting ───────────────────────────────────────────────────────────

def test_every_request_goes_through_the_throttle(monkeypatch):
    """postforme allows 5 requests/second and says so only in a response header
    — nothing in the swagger mentions it. The limiter lives in _request so a new
    call site cannot forget it."""
    calls = []
    monkeypatch.setattr(postforme, "_throttle", lambda: calls.append(1))
    _record(monkeypatch, lambda r: _ok(r, {"data": []}))
    postforme.list_accounts(KEY)
    postforme.get_post_results(KEY, post_id="sp_1")
    assert len(calls) == 2


def test_the_throttle_paces_a_burst_rather_than_dropping_it(monkeypatch):
    """The metrics pass used to fire one call per publication with no pacing,
    so past the fifth it got 429s that were caught and skipped — losing
    snapshots permanently, since the series cannot be backfilled."""
    slept = []
    monkeypatch.setattr(postforme.time, "sleep", lambda s: slept.append(s))
    postforme._recent_calls.clear()
    for _ in range(postforme._RATE_LIMIT_PER_SEC + 2):
        postforme._throttle()
    assert slept, "a burst past the limit must wait, not sail through"
    postforme._recent_calls.clear()


def test_the_throttle_lets_a_quiet_caller_straight_through(monkeypatch):
    slept = []
    monkeypatch.setattr(postforme.time, "sleep", lambda s: slept.append(s))
    postforme._recent_calls.clear()
    postforme._throttle()
    postforme._throttle()
    assert slept == []
    postforme._recent_calls.clear()


# ── reconciliation ──────────────────────────────────────────────────────────

def test_a_post_can_be_found_again_by_the_video_id_we_stamped_on_it(monkeypatch):
    """create_post can fail *after* postforme accepted the post — a timeout, a
    5xx, a non-JSON body. Retrying blind would publish twice for real, so the
    external_id is the only way back to what already exists."""
    seen = _record(monkeypatch, lambda r: _ok(r, {"data": [POST_RESPONSE]}))
    post = postforme.find_post_by_external_id(KEY, external_id="vid_123")
    assert post["id"] == "sp_abc"
    assert seen[0].url.params["external_id"] == "vid_123"


def test_no_such_post_is_none_rather_than_an_error(monkeypatch):
    _record(monkeypatch, lambda r: _ok(r, {"data": []}))
    assert postforme.find_post_by_external_id(KEY, external_id="vid_nope") is None


def test_a_recovered_post_is_scrubbed_like_any_other(monkeypatch):
    _record(monkeypatch, lambda r: _ok(r, {"data": [POST_RESPONSE]}))
    post = postforme.find_post_by_external_id(KEY, external_id="vid_123")
    assert post["social_accounts"][0]["refresh_token"] == "<redacted>"


def _posts_and_results(monkeypatch, posts, results_by_post):
    """Serve GET /social-posts and per-post GET /social-post-results."""
    def respond(request):
        if request.url.path.endswith("/social-post-results"):
            return _ok(request, {"data": results_by_post.get(request.url.params["post_id"], [])})
        return _ok(request, {"data": posts})
    return _record(monkeypatch, respond)


def _post(post_id, created_at, accounts=("spc_yt",)):
    return {"id": post_id, "external_id": "vid_123", "created_at": created_at,
            "social_accounts": [{"id": a, "platform": "youtube"} for a in accounts]}


def _outcome(account, success):
    return {"social_account_id": account, "success": success,
            "error": None if success else {"message": "rejected"}}


def test_a_live_post_beats_a_newer_dead_one_under_the_same_external_id(monkeypatch):
    """A video whose first post failed everywhere and was published again has
    two posts with one external_id. Returning the dead one would make a live
    video look unposted — and invite a third, real post."""
    _posts_and_results(monkeypatch,
                       [_post("sp_dead", "2026-09-19T12:00:00Z"),
                        _post("sp_live", "2026-09-19T10:00:00Z")],
                       {"sp_dead": [_outcome("spc_yt", False)],
                        "sp_live": [_outcome("spc_yt", True)]})
    post = postforme.find_post_by_external_id(KEY, external_id="vid_123")
    assert (post["id"], post["live"]) == ("sp_live", True)


def test_with_only_dead_posts_the_newest_is_returned(monkeypatch):
    _posts_and_results(monkeypatch,
                       [_post("sp_older", "2026-09-18T10:00:00Z"),
                        _post("sp_newer", "2026-09-19T10:00:00Z")],
                       {"sp_older": [_outcome("spc_yt", False)],
                        "sp_newer": [_outcome("spc_yt", False)]})
    post = postforme.find_post_by_external_id(KEY, external_id="vid_123")
    assert (post["id"], post["live"]) == ("sp_newer", False)
    assert post["results"][0]["success"] is False


def test_a_target_that_has_not_reported_keeps_a_post_live(monkeypatch):
    """Results have no pending state — a missing row is the only sign that a
    platform is still processing. That post may yet succeed."""
    _posts_and_results(monkeypatch,
                       [_post("sp_1", "2026-09-19T10:00:00Z", accounts=("spc_yt", "spc_ig"))],
                       {"sp_1": [_outcome("spc_yt", False)]})
    assert postforme.find_post_by_external_id(KEY, external_id="vid_123")["live"] is True


def test_publication_targets_accepts_both_account_shapes():
    """Objects on a fetched post, bare ids on the request we sent."""
    assert postforme.publication_targets(
        {"social_accounts": [{"id": "spc_yt", "platform": "youtube"}, "spc_ig", {"id": ""}]}
    ) == [("spc_yt", "youtube"), ("spc_ig", "")]
    assert postforme.publication_targets({}) == []


def test_the_upload_is_streamed_with_a_content_length_not_chunked(monkeypatch, tmp_path):
    """Streaming is what lets the upload cap be enforced; the explicit length
    keeps httpx from sending the body chunked, which pre-signed storage URLs
    commonly reject."""
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, request=request)

    monkeypatch.setattr(postforme.httpx, "Client", _factory(handler))
    monkeypatch.setattr(postforme, "_UPLOAD_CHUNK_BYTES", 4)
    mp4 = tmp_path / "v.mp4"
    mp4.write_bytes(b"0123456789")
    postforme.upload_media("https://storage.example/signed", str(mp4))
    assert seen[0].headers["Content-Length"] == "10"
    assert "Transfer-Encoding" not in seen[0].headers
    assert seen[0].content == b"0123456789"


def test_an_upload_past_the_cap_is_stopped_as_a_clean_failure(monkeypatch, tmp_path):
    """The cap is what keeps a publish request inside the worker's deadline.
    Hitting it is an ordinary PostformeError, so the route releases the claim
    as for any other upload failure."""
    monkeypatch.setattr(postforme.httpx, "Client",
                        _factory(lambda r: httpx.Response(200, request=r)))
    monkeypatch.setattr(postforme, "_UPLOAD_CHUNK_BYTES", 4)
    clock = iter([0.0, 1.0, postforme.UPLOAD_MAX_SECS + 1])
    monkeypatch.setattr(postforme.time, "monotonic", lambda: next(clock))
    mp4 = tmp_path / "v.mp4"
    mp4.write_bytes(b"0123456789")
    with pytest.raises(postforme.PostformeError, match="longer than 30 minutes"):
        postforme.upload_media("https://storage.example/signed", str(mp4))


def test_every_page_of_posts_is_checked_before_deciding_nothing_is_live(monkeypatch):
    """A live post beyond the first page must still be found — "nothing live"
    is what lets Retry post the video again."""
    monkeypatch.setattr(postforme, "_POST_PAGE", 2)
    dead = [_post(f"sp_d{i}", f"2026-09-1{i}T00:00:00Z") for i in range(3)]
    live = _post("sp_live", "2026-09-01T00:00:00Z")
    pages = [dead[:2], [dead[2], live]]

    def respond(request):
        if request.url.path.endswith("/social-post-results"):
            ok = request.url.params["post_id"] == "sp_live"
            return _ok(request, {"data": [_outcome("spc_yt", ok)]})
        index = int(request.url.params["offset"]) // 2
        return _ok(request, {"data": pages[index] if index < len(pages) else []})

    _record(monkeypatch, respond)
    assert postforme.find_post_by_external_id(KEY, external_id="vid_123")["id"] == "sp_live"
