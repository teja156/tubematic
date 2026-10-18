"""postforme.dev API client — multi-platform social publishing (TMDEV-83).

Deliberately DB-free, like ai_review.py: the API key and base URL arrive as
arguments, so the settings read and the "not configured" 503 stay in the route
that owns them. That keeps this module trivially testable and means a rotated
key applies on the next call with no restart.

Unlike ai_review.py, this module does NOT fail open. A review that silently
does not happen costs nothing; a publish that silently does not happen strands
a video the human believes went out. Every failure raises PostformeError, and
the caller turns it into a status code.

Two facts here were established by probing the live API on 2026-09-05, not read
off the swagger — both would otherwise be found the hard way:

  * Responses carry live OAuth credentials. POST /social-posts nests the whole
    target account per target, including a real access_token and a refresh_token
    with no expiry. Everything returned from this module is already scrubbed;
    see scrub() for why that is here and not at a display boundary.
  * create-upload-url and social-posts both answer 201, while the swagger
    documents 200. Anything checking `== 200` breaks on the happy path.
"""
import json
import os
import threading
import time

import httpx

DEFAULT_BASE_URL = os.environ.get("POSTFORME_BASE", "https://api.postforme.dev/v1")

# Platforms this pipeline knows how to compose content for. postforme supports
# more (x, linkedin, bluesky, threads, pinterest); an account on one of those is
# listed and postable, it just gets no per-platform override.
SUPPORTED_PLATFORMS = ("youtube", "instagram", "tiktok", "facebook")

# Fields postforme returns that must never reach a log, a comment, a DB column
# or the browser. These are the connected channel's own OAuth credentials, and
# the refresh token observed live had no expiry at all.
CREDENTIAL_FIELDS = ("access_token", "refresh_token")

# Fields safe to hand to the dashboard. An allowlist, never a blocklist: a new
# credential-bearing field added upstream must not leak by default.
PUBLIC_ACCOUNT_FIELDS = ("id", "platform", "username", "profile_photo_url", "status")

# Measured live 2026-09-06, and documented NOWHERE — it is in the response
# headers (x-ratelimit-limit: 5, resetting every second) and absent from the
# swagger entirely. Exceeding it is a 429.
#
# Enforced here, in the one chokepoint every call goes through, rather than at
# each call site: a burst is easy to reintroduce accidentally (the metrics pass
# used to loop over publications with no pacing at all, silently dropping
# snapshots past the fifth), and a limiter that has to be remembered is one that
# eventually is not.
# Per process, not per install: the Flask API and the render worker are separate
# containers, so each keeps its own window and a simultaneous burst from both
# could still exceed 5/s. Not worth coordinating — the worker polls hourly, the
# API only on a human action, and a 429 is caught and retried next pass. Say so
# here rather than leaving the next reader to discover it.
_RATE_LIMIT_PER_SEC = 5
_rate_lock = threading.Lock()
_recent_calls: list = []

_TIMEOUT_SECS = 30.0
# The mp4 is the slow one. Measured live: a 153MB / 250s render took 51s at
# 3.0 MB/s, so this is roughly a 10x margin on the largest video the pipeline
# is expected to produce.
_UPLOAD_TIMEOUT_SECS = 600.0
# ...but that timeout applies per network operation, not to the upload as a
# whole, so on its own nothing bounds how long an upload can run. This does
# (TMDEV-97). It exists so a publish request always finishes before the
# worker's publish deadline (worker.py::_PUBLISH_TIMEOUT_SECS, an hour): past
# that deadline the worker fails an in-flight publish, and a create_post
# arriving later would attach a live post to a video already moved on by Retry.
# Worst case is this, plus one stalled write and the response read at
# _UPLOAD_TIMEOUT_SECS each, plus the short calls around it — a test pins that
# the sum stays under the deadline. 30 minutes is still ~35x the measured time.
UPLOAD_MAX_SECS = 1800.0
_UPLOAD_CHUNK_BYTES = 1024 * 1024


class PostformeError(Exception):
    """Any postforme call that did not succeed. `message` is already scrubbed."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


def scrub(obj):
    """Recursively replace OAuth credentials with a marker.

    Applied to every response before it is returned, rather than at whatever
    boundary happens to render it. The publish path persists errors into
    video_publications.error and posts comments on every outcome — that comment
    path is exactly how a Gemini key reached user-visible storage in TMDEV-46 —
    so "scrub at the edge" leaves too many edges to get right. Returns a copy;
    the caller's input is never mutated.

    Empty and null values pass through untouched: replacing them would invent
    the appearance of a secret where there is none.
    """
    if isinstance(obj, dict):
        return {k: ("<redacted>" if k in CREDENTIAL_FIELDS and v else scrub(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [scrub(v) for v in obj]
    return obj


def public_account(account: dict) -> dict:
    """Project a postforme account down to what the dashboard may see."""
    return {k: account.get(k) for k in PUBLIC_ACCOUNT_FIELDS}


def _throttle() -> None:
    """Block until another request would stay inside 5/second.

    Thread-safe because the Flask process is threaded=True: a publish and an
    analytics refresh can genuinely overlap, and two independent limiters would
    let the pair exceed the budget together.
    """
    with _rate_lock:
        while True:
            now = time.monotonic()
            _recent_calls[:] = [t for t in _recent_calls if now - t < 1.0]
            if len(_recent_calls) < _RATE_LIMIT_PER_SEC:
                _recent_calls.append(now)
                return
            time.sleep(1.0 - (now - _recent_calls[0]))


def _redact(text: str, api_key: str) -> str:
    """Belt-and-braces on top of never putting the key in a URL. Mirrors
    ai_review.py's helper of the same name."""
    if not api_key:
        return text
    return text.replace(api_key, "***REDACTED***")


def _error_message(resp: httpx.Response, api_key: str) -> str:
    """Build a persistable message from a failed response.

    The body is scrubbed before anything is read out of it, because an error
    payload can echo the submitted request — and that request names the
    account whose credentials postforme happily includes elsewhere.
    """
    try:
        body = scrub(resp.json())
        detail = None
        if isinstance(body, dict):
            error = body.get("error")
            if isinstance(error, dict):
                detail = error.get("message")
            # Some routes answer in the framework's own shape, a top-level
            # `message` (probed: a disabled platform's 404 on auth-url). It is
            # the actionable part, so show it rather than the JSON around it.
            if not detail and isinstance(body.get("message"), str):
                detail = body["message"]
        detail = detail or json.dumps(body)[:400]
    except Exception:
        detail = resp.text[:400]
    return _redact(f"postforme returned HTTP {resp.status_code}: {detail}", api_key)


def _request(method: str, path: str, *, api_key: str, base_url: str | None = None,
             json_body: dict | None = None, params: dict | None = None,
             timeout: float = _TIMEOUT_SECS) -> dict:
    """One authenticated call. Returns the scrubbed JSON body.

    The key travels as a header and never as a query param: httpx embeds the
    request URL in its error strings, and those have reached the dashboard-
    visible comments table before (TMDEV-46).
    """
    url = f"{(base_url or DEFAULT_BASE_URL).rstrip('/')}{path}"
    _throttle()
    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(
                method, url,
                headers={"Authorization": f"Bearer {api_key}"},
                json=json_body, params=params,
            )
    except Exception as e:
        # Includes httpx.ConnectError/TimeoutException, and the two paste
        # failures that don't look like network errors: LocalProtocolError
        # subclasses HTTPError, while UnicodeEncodeError is not an httpx
        # exception at all (TMDEV-52).
        raise PostformeError(_redact(f"postforme request failed: {e}", api_key)) from None

    if resp.status_code >= 300:
        raise PostformeError(_error_message(resp, api_key), resp.status_code)

    if not resp.content:
        return {}
    try:
        return scrub(resp.json())
    except ValueError:
        raise PostformeError("postforme returned a non-JSON response", resp.status_code) from None


# ── accounts ─────────────────────────────────────────────────────────────────

def list_accounts(api_key: str, *, base_url: str | None = None) -> list:
    """Every account connected to this postforme key, scrubbed.

    Note this is postforme's whole list, not Tubematic's allowlist — the caller
    reconciles it against settings.publishing_accounts.
    """
    body = _request("GET", "/social-accounts", api_key=api_key, base_url=base_url,
                    params={"limit": 100})
    return body.get("data", [])


# Asked for on every connect, never chosen by the caller. postforme grants
# `posts` alone by default, and an account connected without `feeds` publishes
# perfectly while reporting no metric, silently and forever — on Instagram the
# feed still answers 200, so nothing ever flags it (docs/developer/14-publishing.md,
# "Connecting accounts"). A permission changes only by reconnecting.
CONNECT_PERMISSIONS = ("posts", "feeds")


def create_auth_url(api_key: str, *, platform: str, permissions, base_url: str | None = None) -> dict:
    """Mint a consent URL that connects a new account. Returns {platform, url}.

    Side-effect-free until someone completes the consent. The URL's `state` is
    single-use and expires, so mint one per click and never cache it. postforme
    ignores any redirect parameter (probed), so the flow ends on its own callback
    page and the user comes back by hand.
    """
    return _request("POST", "/social-accounts/auth-url", api_key=api_key, base_url=base_url,
                    json_body={"platform": platform, "permissions": list(permissions)})


# ── media ────────────────────────────────────────────────────────────────────

def create_upload_url(api_key: str, *, base_url: str | None = None) -> dict:
    """Reserve a storage slot. Returns {upload_url, media_url}.

    Takes no request body — the swagger's own example sends none, and the
    ticket's "{filename, content_type}" was wrong. Answers 201.
    """
    return _request("POST", "/media/create-upload-url", api_key=api_key, base_url=base_url)


def upload_media(upload_url: str, file_path: str, *, content_type: str = "video/mp4") -> None:
    """PUT the file to the pre-signed URL.

    No Authorization header: upload_url is already signed, and it points at a
    storage host rather than the API, so sending the key would hand it to a
    third party for nothing. The signature is short-lived, so this must follow
    create_upload_url promptly.

    Streamed in chunks so UPLOAD_MAX_SECS can be enforced between them. The
    Content-Length header is set explicitly: without it httpx sends a streamed
    body chunked, which pre-signed storage URLs commonly reject.
    """
    try:
        size = os.path.getsize(file_path)
        fh = open(file_path, "rb")
    except OSError as e:
        raise PostformeError(f"could not read the video file: {e}") from None

    deadline = time.monotonic() + UPLOAD_MAX_SECS

    def chunks():
        while chunk := fh.read(_UPLOAD_CHUNK_BYTES):
            if time.monotonic() > deadline:
                raise PostformeError(
                    f"media upload took longer than {int(UPLOAD_MAX_SECS // 60)} minutes "
                    f"and was stopped; nothing was posted")
            yield chunk

    try:
        with fh, httpx.Client(timeout=_UPLOAD_TIMEOUT_SECS) as client:
            resp = client.put(upload_url, content=chunks(),
                              headers={"Content-Type": content_type,
                                       "Content-Length": str(size)})
    except PostformeError:
        raise
    except Exception as e:
        raise PostformeError(f"media upload failed: {e}") from None

    if resp.status_code >= 300:
        raise PostformeError(f"media upload returned HTTP {resp.status_code}", resp.status_code)


# ── posts ────────────────────────────────────────────────────────────────────

def create_post(api_key: str, *, caption: str, social_account_ids: list, media_url: str,
                platform_configurations: dict, external_id: str,
                scheduled_at: str | None = None,
                base_url: str | None = None) -> dict:
    """Post to every named account in one call. Answers 201.

    With no `scheduled_at` the field is left out entirely, not set to "now":
    it is nullable and absent means publish immediately. With one (a UTC ISO
    string ending in Z — a string without an offset would be read in
    postforme's own zone), postforme holds the post and sends it at that time.
    Media attached to a scheduled post is kept until then; only unattached
    uploads expire after 24h.

    `external_id` carries our video_id. It is the durable join key for the
    analytics feed filter, and the recovery path if this process dies between
    a successful POST and the DB write (GET /social-posts?external_id=...).
    """
    body = {
        "caption": caption,
        "social_accounts": social_account_ids,
        "media": [{"url": media_url}],
        "platform_configurations": platform_configurations,
        "external_id": external_id,
    }
    if scheduled_at:
        body["scheduled_at"] = scheduled_at
    return _request("POST", "/social-posts", api_key=api_key, base_url=base_url, json_body=body)


def delete_post(api_key: str, *, post_id: str, base_url: str | None = None) -> None:
    """Cancel a scheduled post.

    postforme refuses with 400 once the post is no longer `scheduled` (it is
    already going out) and 404 when it does not exist; both surface as
    PostformeError with that status_code. It also answers 200
    `{"success": false}` when its own delete fails, which is raised too — the
    post is still scheduled then.
    """
    out = _request("DELETE", f"/social-posts/{post_id}", api_key=api_key, base_url=base_url)
    if out.get("success") is not True:
        raise PostformeError("postforme did not delete the scheduled post", 200)


_POST_PAGE = 50
_POST_LOOKUP_CAP = 500


def find_post_by_external_id(api_key: str, *, external_id: str,
                             base_url: str | None = None) -> dict | None:
    """The post we stamped with this video_id, if postforme has one.

    The reconciliation path for an ambiguous create_post: a timeout, a 5xx or a
    non-JSON body can all arrive *after* postforme accepted the post, so the
    caller cannot know whether one exists. Retrying blind would publish twice
    for real. This is why every post carries `external_id = video_id`.

    More than one post can carry the same external_id: a video whose post failed
    on every account and was then published again has two. So every match is
    checked, and a live one wins over a dead one — otherwise an old dead post
    returned first would hide the live one. Among equals, the newest by
    `created_at` wins (a required field on every post in the swagger).

    The chosen post comes back with two extra keys: `results` (its per-target
    outcomes, already fetched to judge liveness) and `live` (see is_live_post).
    """
    posts = []
    # Every page, not just the first: a live post past it would otherwise go
    # unseen, and "nothing live" is what lets Retry post again. Capped so a
    # runaway listing cannot spin; one video reaching the cap would take
    # hundreds of failed publishes.
    for offset in range(0, _POST_LOOKUP_CAP, _POST_PAGE):
        body = _request("GET", "/social-posts", api_key=api_key, base_url=base_url,
                        params={"external_id": external_id, "limit": _POST_PAGE,
                                "offset": offset})
        page = body.get("data", [])
        posts += [p for p in page if isinstance(p, dict) and p.get("id")]
        if len(page) < _POST_PAGE:
            break
    if not posts:
        return None
    for post in posts:
        post["results"] = get_post_results(api_key, post_id=post["id"], base_url=base_url)
        post["live"] = is_live_post(post, post["results"])
    pool = [p for p in posts if p["live"]] or posts
    return max(pool, key=lambda p: str(p.get("created_at") or ""))


def is_live_post(post: dict, results: list) -> bool:
    """Whether a post is published somewhere, or may still be.

    Live = at least one target succeeded, or some target has not reported yet
    (results carry no pending state, so a missing row is the only sign of one).
    Dead = every target reported, and every one failed.
    """
    if any(r.get("success") for r in results):
        return True
    reported = {r.get("social_account_id") for r in results}
    return any(account_id not in reported for account_id, _ in publication_targets(post))


def publication_targets(post: dict) -> list:
    """[(social_account_id, platform)] for every account a post targets.

    The list is objects on a fetched post and bare ids on the request we sent,
    so accept either rather than assuming the shape.
    """
    targets = []
    for account in post.get("social_accounts") or []:
        if isinstance(account, str):
            targets.append((account, ""))
        elif isinstance(account, dict):
            targets.append((account.get("id", ""), account.get("platform", "")))
    return [t for t in targets if t[0]]


def get_post_results(api_key: str, *, post_id: str, base_url: str | None = None) -> list:
    """Per-target outcomes for one post.

    There is no "pending" state in this payload: a target that has not
    published yet simply has no row. Callers decide completion by counting
    rows against the number of targets, never by reading a status field.
    """
    body = _request("GET", "/social-post-results", api_key=api_key, base_url=base_url,
                    params={"post_id": post_id, "limit": 100})
    return body.get("data", [])


# ── analytics ────────────────────────────────────────────────────────────────

def get_account_feed(api_key: str, *, social_account_id: str, social_post_id: str | None = None,
                     limit: int = 50, cursor: str | None = None,
                     base_url: str | None = None) -> dict:
    """One account's posts with metrics attached.

    There is no per-post analytics endpoint, but this one filters server-side
    by social_post_id — which is what keeps analytics cheap and makes the
    account's unrelated posts a non-issue.
    """
    params = {"expand": "metrics", "limit": limit}
    if social_post_id:
        params["social_post_id"] = social_post_id
    if cursor:
        params["cursor"] = cursor
    return _request("GET", f"/social-account-feeds/{social_account_id}",
                    api_key=api_key, base_url=base_url, params=params)


# Per-platform metric names for the common subset stored as columns. Everything
# else lives in video_metrics.raw_json — aggregating "views" across platforms is
# defensible, summing platform-specific metrics is not.
#
# Facebook is the awkward one and the reason this is a table rather than a
# straight-through copy: it has no `likes` (reactions_total is the nearest
# equivalent) and no `views` (video_views, falling back to media_views).
_METRIC_FIELDS = {
    "youtube":   {"views": ("views",), "likes": ("likes",),
                  "comments": ("comments",), "shares": ("shares",)},
    "instagram": {"views": ("views",), "likes": ("likes",),
                  "comments": ("comments",), "shares": ("shares",)},
    "tiktok":    {"views": ("view_count",), "likes": ("like_count",),
                  "comments": ("comment_count",), "shares": ("share_count",)},
    "facebook":  {"views": ("video_views", "media_views"), "likes": ("reactions_total",),
                  "comments": ("comments",), "shares": ("shares",)},
}

METRIC_COLUMNS = ("views", "likes", "comments", "shares")

# Privacy is per platform because the platforms genuinely differ: YouTube has
# three states, TikTok two, and Instagram/Facebook none at all (their DTOs have
# no such field — a Reel is public or it is not posted). One shared control
# would have to either offer "unlisted" where it cannot exist or silently map
# it onto a state the user did not pick.
#
# Order matters — the first entry is the default, and it matches the
# `default: "public"` postforme documents on both fields.
PRIVACY_OPTIONS = {
    "youtube": ("public", "unlisted", "private"),
    "tiktok": ("public", "private"),
}


def extract_metrics(platform: str, metrics: dict | None) -> dict:
    """Map a platform's metrics payload onto the common subset.

    A metric that is absent comes back None, not 0 — "not reported" and
    "reported as zero" are different claims, and a chart that reads a missing
    value as a real zero is lying about the data.

    An unrecognised platform yields all-None rather than raising: a new
    platform appearing upstream must not break the metrics poll for every other
    publication in the same pass.
    """
    fields = _METRIC_FIELDS.get(platform, {})
    metrics = metrics or {}
    out = {}
    for column in METRIC_COLUMNS:
        value = None
        for name in fields.get(column, ()):
            if metrics.get(name) is not None:
                value = metrics[name]
                break
        out[column] = value
    return out


# ── content mapping ──────────────────────────────────────────────────────────

def compose_caption(title: str, description: str) -> str:
    """Title, blank line, description — for the platforms that have no title.

    Instagram, TikTok and Facebook show a single caption, and it is the text
    people actually read. Sending a bare title there produces a worse post than
    no post at all.
    """
    title, description = (title or "").strip(), (description or "").strip()
    return f"{title}\n\n{description}".strip() if description else title


def build_platform_configurations(platforms, title: str, description: str,
                                  privacy: dict | None = None) -> dict:
    """Per-platform content overrides for one publish.

    An unmapped platform is omitted entirely rather than sent an empty
    override. postforme silently accepts anything it is given — probed live, a
    deliberately bogus field returned 201 and was stored verbatim — so there is
    no server-side safety net here at all. Every field name emitted below is
    pinned by test_postforme.py against a fixture generated from the live
    swagger; that test is the only thing standing between a typo and, say, an
    AI-disclosure flag that is silently never set.
    """
    caption = compose_caption(title, description)
    title = (title or "").strip()
    privacy = privacy or {}
    for platform, choice in privacy.items():
        allowed = PRIVACY_OPTIONS.get(platform)
        # Refused rather than quietly downgraded: postforme accepts anything it
        # is given, so an unsupported value would be stored and then ignored,
        # and the post would come out public with nothing saying why.
        if allowed is not None and choice not in allowed:
            raise ValueError(
                f"{platform} does not support privacy {choice!r} — "
                f"expected one of {', '.join(allowed)}")
    configs = {}
    for platform in platforms:
        if platform == "youtube":
            # The one platform with real title/description fields. It also has
            # a `caption`, which is not what YouTube shows — don't send it.
            configs[platform] = {
                "title": title,
                "description": (description or "").strip(),
                # Tubematic output is AI-generated. Hardcoded rather than
                # exposed as a setting: it is a platform-policy requirement,
                # and a knob only invites turning it off.
                "contains_synthetic_media": True,
                "privacy_status": privacy.get(platform, PRIVACY_OPTIONS[platform][0]),
            }
        elif platform == "tiktok":
            # TikTok has BOTH a title and a caption, unlike Instagram/Facebook.
            configs[platform] = {
                "title": title,
                "caption": caption,
                "is_ai_generated": True,
                "privacy_status": privacy.get(platform, PRIVACY_OPTIONS[platform][0]),
            }
        elif platform in ("instagram", "facebook"):
            # placement is explicit, not left to postforme's default. Every
            # Tubematic render is 1080x1920, and a 9:16 video dropped on the
            # feed instead of Reels is the wrong product — letterboxed, and
            # outside the surface short-form video is actually watched on.
            #
            # There is no equivalent for YouTube: neither postforme nor the
            # YouTube Data API has a Shorts flag. YouTube infers it from the
            # file — vertical aspect AND duration <= 3 minutes. Aspect is
            # always right here; duration is not enforced anywhere (TMDEV-81
            # left the ~450-word budget to prose in the skill), so a long
            # video silently posts as a regular video.
            configs[platform] = {"caption": caption, "placement": "reels"}
    return configs
