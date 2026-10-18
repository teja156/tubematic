"""Live API-key validation, run the moment a key is typed (TMDEV-52).

`ask_field` never ran a Field's validator for `kind="secret"` fields, so a
typo'd or revoked key was stored unchecked and only surfaced much later as
a paid-call failure deep in the pipeline — a 401 mid-voicing, a fail-open AI
review that silently ships an unreviewed video, or `generate_image` breaking
after a topic is already approved. checks.py only ever tested *presence*.

Each service gets its own checker, because the four disagree on how they
reject a bad key. These shapes were observed by probing every endpoint with a
deliberately bogus token, not read off a docs page:

    ElevenLabs      401  {"detail": {"status": "invalid_api_key", ...}}
    Gemini          400  {"error": {..., "details": [{"reason": "API_KEY_INVALID"}]}}
    OpenAI          401  {"error": {"code": "invalid_api_key", ...}}
    yt-transcript   401  Unauthorized, token is invalid        (plain text)

Gemini is the one that matters: it answers **400**, not 401. A shared
"401/403 means invalid" rule would classify every bad Gemini key as unknown
and accept it silently — the most consequential key of the four, and exactly
the failure this module exists to prevent. So the mappings deliberately stay
per service instead of collapsing into one status-code table.

The three outcomes are load-bearing, not decoration. A confirmed `INVALID` is
a hard gate (onboard/prompt.py re-asks until it clears), so anything merely
*unproven* — a timeout, a DNS failure, a 5xx — must come back `UNKNOWN` and be
accepted with a warning. Gating on those would make an offline or proxied
install impossible and turn any provider outage into an unpassable wizard.

Every key travels as a **header**, never a URL query parameter: httpx embeds
the request URL in its error strings, and worker.py persists those verbatim
into the dashboard-visible comments table — which is how a Gemini key leaked
once already (TMDEV-46).
"""
import re
from dataclasses import dataclass
from typing import Callable

# Long enough for a cold TLS handshake to a busy provider, short enough that a
# human sitting at the prompt isn't left wondering. Deliberately shorter than
# the 30s the transcript fetch uses — nothing is blocking a person there.
TIMEOUT_SECS = 10

VALID = "valid"
INVALID = "invalid"
UNKNOWN = "unknown"


@dataclass
class KeyCheck:
    status: str          # VALID | INVALID | UNKNOWN
    detail: str = ""     # shown to the user — never contains the key itself


class _Unreachable(Exception):
    """Transport-level failure. Proves nothing about the key either way."""


# Anything outside printable ASCII. Line breaks and NULs genuinely cannot go in
# an HTTP header value; a tab technically can, but no provider issues keys
# containing one, so "that looks like a paste artefact" is a more useful answer
# than a generic 401. Interior *spaces* are deliberately allowed through: httpx
# sends them fine, so the provider gets to reject them and we learn something
# real instead of guessing.
_UNSENDABLE = re.compile(r"[^\x20-\x7e]")


def malformed_reason(key: str) -> str:
    """Why `key` can't even be put on the wire, or "" if it can.

    This has to run *before* the request, because the two ways a bad paste
    fails are both worse than a rejection: httpx raises LocalProtocolError,
    which subclasses httpx.HTTPError and so was being caught as "provider
    unreachable" → UNKNOWN → silently accepted; and a non-ASCII character
    raises UnicodeEncodeError, which isn't an httpx error at all and escaped
    the checker entirely, crashing the wizard with a traceback. Neither is an
    unreachable provider; both are invalid input, and are reported as such.
    """
    bad = _UNSENDABLE.search(key)
    if not bad:
        return ""
    char = bad.group()
    shown = {"\n": "a line break", "\r": "a carriage return", "\t": "a tab"}.get(
        char, f"a non-printable character (0x{ord(char):02x})")
    return (f"Key contains {shown} — it looks like a copy/paste artefact. "
            "Re-copy the key and try again.")


def _send(method: str, url: str, *, headers: dict, json_body=None, transport=None):
    """One request, with httpx imported at call time.

    Inline rather than module-level so importing this module (which
    onboard/config.py does, to hang checkers off its Field specs) never drags
    httpx into checks.py and every onboard test — matching `writable_parent`'s
    inline `import os`. `transport` exists so tests can hand in an
    httpx.MockTransport; nothing in the wizard passes it.
    """
    import httpx

    try:
        with httpx.Client(timeout=TIMEOUT_SECS, transport=transport) as client:
            return client.request(method, url, headers=headers, json=json_body)
    except httpx.HTTPError as exc:
        raise _Unreachable(type(exc).__name__) from exc


def _unreachable(service: str, exc: _Unreachable) -> KeyCheck:
    return KeyCheck(UNKNOWN, f"Could not reach {service} ({exc}) — key not verified.")


def _accepted_or_unknown(service: str, resp) -> KeyCheck:
    """Fallback once a service's own bad-key signature has been ruled out.

    429 counts as proof the key is good: the request got far enough to be rate-
    or quota-limited, which only happens after auth. A Gemini 429 in particular
    usually means "this project has no quota for this model", never a bad key.
    """
    if resp.is_success or resp.status_code == 429:
        return KeyCheck(VALID)
    return KeyCheck(UNKNOWN, f"{service} answered HTTP {resp.status_code} — key not verified.")


def _scrub(text: str, key: str) -> str:
    """Redact the key from anything a provider hands back.

    Every rejection body observed so far is key-free except OpenAI's (handled
    separately), so this is a guard rather than a live fix — but a provider
    error string quoting the credential back, printed to a terminal and
    scrolled into a transcript, is exactly how a Gemini key leaked once
    already (TMDEV-46). Always scrub *before* truncating: truncating first can
    split the key and leave the tail unreplaced.
    """
    return text.replace(key, "***") if key else text


def _message(resp, *path: str) -> str:
    """A provider's own error text at `path`, or "" if the body isn't the
    JSON shape we expect. Surfacing the provider's wording lets a user tell
    "wrong key" from "wrong permissions" without this module having to build
    an error taxonomy of its own."""
    try:
        node = resp.json()
    except ValueError:
        return ""
    for key in path:
        if not isinstance(node, dict):
            return ""
        node = node.get(key)
    return node.strip() if isinstance(node, str) else ""


# ── Per-service checkers ────────────────────────────────────────────────────

# The permissions Tubematic's ElevenLabs key must carry, each paired with the
# cheapest endpoint that exercises it. Probed live: all four paths answer 401
# to a bogus key (a wrong path 404s instead, so a 401 proves the path is real).
#
# The text-to-speech probe deliberately names a voice that cannot exist. Auth
# runs *before* voice lookup — verified, the bogus-key probe 401s rather than
# 404s — so this never reaches generation and never spends a credit. Its one
# soft spot: if ElevenLabs ever validated the voice before the permission gate,
# a key lacking text_to_speech would come back "voice not found" and be read as
# having the permission. That errs toward accepting, which under the hard gate
# is the harmless direction.
_ELEVENLABS_PROBES = [
    ("text-to-speech", "POST",
     "https://api.elevenlabs.io/v1/text-to-speech/zzzzINVALIDvoiceZZZZ", {"text": "."}),
    ("voices (read)", "GET", "https://api.elevenlabs.io/v1/voices", None),
    ("projects (read)", "GET", "https://api.elevenlabs.io/v1/studio/projects", None),
    ("pronunciation dictionaries (read)", "GET",
     "https://api.elevenlabs.io/v1/pronunciation-dictionaries", None),
]


def check_elevenlabs(key: str, *, transport=None) -> KeyCheck:
    """Verify the key exists *and* carries every permission Tubematic needs.

    ElevenLabs keys are scoped at creation (`permissions: ["text_to_speech",
    ...]`), so "the key is real" and "the key can do the job" are different
    questions — a key that authenticates perfectly can still fail every call
    the pipeline makes. Both failures are caught here, and told apart by
    `detail.status`: "invalid_api_key" means the credential is wrong,
    "missing_permissions" means it is right but under-scoped. Collapsing the
    two is a documented real-world installer bug.

    Every permission is probed rather than stopping at the first gap, so the
    user is told the complete list once instead of discovering them one
    re-entry at a time. A wrong *key*, by contrast, short-circuits — the
    remaining probes would all say the same thing.
    """
    missing = []
    for label, method, url, body in _ELEVENLABS_PROBES:
        try:
            resp = _send(method, url, headers={"xi-api-key": key},
                         json_body=body, transport=transport)
        except _Unreachable as exc:
            return _unreachable("ElevenLabs", exc)

        if resp.status_code == 401:
            if _message(resp, "detail", "status") == "missing_permissions":
                missing.append(label)
                continue
            return KeyCheck(INVALID, _scrub(_message(resp, "detail", "message"), key)
                            or "Invalid API key.")

        # Unlike the single-shot checkers, 429 is NOT proof here: a rate limit
        # can land before the permission gate, so it says nothing about this
        # particular scope. Same for a 5xx. Neither is evidence, so neither
        # may silently count as "permission present".
        if resp.status_code == 429 or resp.status_code >= 500:
            return KeyCheck(UNKNOWN,
                            f"ElevenLabs answered HTTP {resp.status_code} while checking "
                            f"{label} — key not verified.")

        # Anything else (2xx, or the 4xx from the deliberately bogus voice)
        # got past both auth and the permission gate.

    if missing:
        return KeyCheck(INVALID, "Key is missing required permission(s): "
                                 + ", ".join(missing)
                                 + ". Add them at elevenlabs.io → Profile → API Keys.")
    return KeyCheck(VALID)


def _gemini_rejected_the_key(resp) -> bool:
    """Gemini answers 400 for a bad key — and 400 for plenty of unrelated
    things too — so the status code alone cannot decide. The discriminator is
    the ErrorInfo detail's `reason`, which is why this looks for that and
    ignores the status entirely. A success body has no `error` key, so it
    falls through to False on its own."""
    try:
        body = resp.json()
    except ValueError:
        return False
    error = body.get("error") if isinstance(body, dict) else None
    details = error.get("details", []) if isinstance(error, dict) else []
    if not isinstance(details, list):
        return False
    return any(isinstance(d, dict) and d.get("reason") == "API_KEY_INVALID" for d in details)


# The Gemini surface Tubematic depends on, with the model that exercises it.
# Image generation used to be probed here too; Gemini no longer draws images
# (TMDEV-165). Keep in sync with onboard/config.py's DEFAULT_AI_REVIEW_MODEL —
# duplicated rather than imported because config.py imports *this* module to
# hang checkers off its Field specs, matching the repo's "# Keep in sync"
# convention for constants that span process boundaries.
_GEMINI_CAPABILITY_PROBES = [
    ("AI review and topic mining", "gemini-2.5-flash",
     "AI review fails open, so this would surface as videos quietly shipping unreviewed "
     "rather than as an error"),
]


def _gemini_capability_warnings(key: str, transport) -> list:
    """Which of Tubematic's Gemini surfaces look unusable on this key.

    Listing models proves the key is real and nothing more. A depleted balance
    429s `generateContent` while `countTokens` and `files.list` keep answering
    200, so a zero-balance key sails through the identity check and then fails
    the first real call, whether that call is mining or the AI review.

    The AI review also uploads the video through the Files API, which 429s
    alongside `generateContent` on a depleted balance, so the text-model probe
    stands in for it rather than opening a resumable upload session here.

    Probed with an empty body: auth is evaluated before both body validation
    and model resolution (verified — a bogus key against a nonexistent model
    still answers API_KEY_INVALID rather than NOT_FOUND), so a usable key falls
    out at the missing-`contents` 400 without generating anything or spending
    anything.

    Any 429 counts as "could not confirm" rather than being decoded further:
    Google's quota-exhausted body shape can't be verified from here without an
    actually-depleted key, and guessing at it would trade a vague-but-true
    warning for a confident-but-unfounded one.
    """
    warnings = []
    for label, model, consequence in _GEMINI_CAPABILITY_PROBES:
        url = (f"https://generativelanguage.googleapis.com/v1beta/models/"
               f"{model}:generateContent")
        try:
            resp = _send("POST", url, headers={"x-goog-api-key": key},
                         json_body={}, transport=transport)
        except _Unreachable:
            # The key already proved itself on the listing call; a flaky
            # follow-up request is not evidence of anything.
            continue
        if resp.status_code in (403, 404, 429):
            warnings.append(f"{label} (HTTP {resp.status_code} from {model}) — {consequence}")
    return warnings


def check_gemini(key: str, *, transport=None) -> KeyCheck:
    """Identity is the gate; the per-capability results are only ever warnings.

    Not hard rejections, deliberately: the key is optional (TMDEV-165). Its
    only uses are AI review — off by default, and skipped outright when no key
    is set (renderer/api/worker.py's
    `if not gemini_review_enabled or not gemini_api_key`) — and the mining
    strategy, which is off without a key. Blocking here would turn an optional
    key into a required one for anyone whose Gemini account has a quota gap.

    Warning is still worth it precisely *because* review is optional and
    forgiving: it fails open, advancing the video to VIDEO_READY regardless, so
    a quota gap there never surfaces as an error at runtime. This prompt may be
    the only place it is ever mentioned.
    """
    try:
        resp = _send("GET", "https://generativelanguage.googleapis.com/v1beta/models",
                     headers={"x-goog-api-key": key}, transport=transport)
    except _Unreachable as exc:
        return _unreachable("Gemini", exc)

    if _gemini_rejected_the_key(resp):
        return KeyCheck(INVALID, _scrub(_message(resp, "error", "message"), key)
                        or "API key not valid.")

    identity = _accepted_or_unknown("Gemini", resp)
    if identity.status != VALID:
        return identity

    warnings = _gemini_capability_warnings(key, transport)
    if warnings:
        return KeyCheck(UNKNOWN, "Key is valid, but these could not be confirmed on it: "
                                 + "; ".join(warnings) + ".")
    return KeyCheck(VALID)


def check_openai(key: str, *, transport=None) -> KeyCheck:
    """Probe the one thing Tubematic uses an OpenAI key for: image generation.

    Deliberately NOT `GET /v1/models`. That endpoint needs `api.model.read`,
    a permission the pipeline never uses, so a restricted key would fail it
    while working fine — and, worse, an under-scoped key that *also* can't
    generate images would have to be reported as either a false rejection or a
    false "Key verified". Probing `POST /v1/images/generations` collapses both
    into one honest answer, because it is exactly the call `generate_image`
    makes (mcp/server.py's OPENAI_IMAGES_URL).

    The body is empty on purpose: auth is evaluated before body validation
    (probed — a bogus key on an empty body answers 401, not 400), so a
    permitted key falls out at the missing-`prompt` 400 without generating an
    image or spending anything.
    """
    try:
        resp = _send("POST", "https://api.openai.com/v1/images/generations",
                     headers={"Authorization": f"Bearer {key}"},
                     json_body={}, transport=transport)
    except _Unreachable as exc:
        return _unreachable("OpenAI", exc)

    if resp.status_code in (401, 403):
        code = _message(resp, "error", "code")
        message = _message(resp, "error", "message")
        if code == "insufficient_permissions" or "insufficient permissions" in message.lower():
            # The key is real, but it cannot do the only job it is here for.
            return KeyCheck(INVALID, "Key authenticated but lacks permission for image "
                                     "generation (POST /v1/images/generations). Grant it on "
                                     "the key at platform.openai.com → API keys.")
        # The one provider message that must NOT be surfaced: OpenAI echoes a
        # masked slice of the submitted key back ("Incorrect API key provided:
        # sk-abcd*****wxyz"), which is still twelve real characters of a live
        # secret. The other services' messages are key-free.
        return KeyCheck(INVALID, f"OpenAI rejected the key (HTTP {resp.status_code}) — "
                                 "the key itself is wrong.")

    # A 429 can be applied before the permission gate, so it is not proof the
    # key may generate images — same reasoning as the ElevenLabs probes.
    if resp.status_code == 429 or resp.status_code >= 500:
        return KeyCheck(UNKNOWN, f"OpenAI answered HTTP {resp.status_code} — key not verified.")

    # 400 (the empty body being rejected) means auth and permission both passed.
    return KeyCheck(VALID)


def check_youtube_transcript(key: str, *, transport=None) -> KeyCheck:
    """youtube-transcript.io publishes no account/usage endpoint, so the
    transcript endpoint itself is the probe — called with an empty id list.
    It rejects on auth *before* validating the body (verified against a bogus
    token), so a bad key still 401s while a good one fetches nothing and spends
    no transcript quota. Costs one of its 5-requests-per-10s rate-limit slots.
    """
    try:
        resp = _send("POST", "https://www.youtube-transcript.io/api/transcripts",
                     headers={"Authorization": f"Basic {key}",
                              "Content-Type": "application/json"},
                     json_body={"ids": []}, transport=transport)
    except _Unreachable as exc:
        return _unreachable("youtube-transcript.io", exc)

    if resp.status_code == 401:
        # Plain text, not JSON, on this one.
        return KeyCheck(INVALID, _scrub(resp.text.strip(), key)[:200]
                        or "Unauthorized, token is invalid.")
    if resp.status_code == 400:
        # Auth passed and only the empty id list was rejected — which is
        # precisely what this probe is asking for.
        return KeyCheck(VALID)
    return _accepted_or_unknown("youtube-transcript.io", resp)


def check_postforme(key: str, *, transport=None) -> KeyCheck:
    """Probe the account listing — the cheapest read-only endpoint (TMDEV-83).

    Deliberately a GET against /social-accounts and nothing else: this key
    grants posting to real social accounts, so a checker that could publish
    while validating would be a catastrophic surprise.

    The discriminator is `error.code`, never the status. postforme answers 401
    for two quite different things — `invalid_key` (the credential is bad) and
    `missing_credentials` (no Authorization header reached it at all). The
    second means this function failed to send the header, i.e. our bug: the key
    it was handed was never judged, so reporting INVALID would reject a good
    key on our own defect. Both observed live 2026-09-05.
    """
    try:
        resp = _send("GET", "https://api.postforme.dev/v1/social-accounts",
                     headers={"Authorization": f"Bearer {key}"}, transport=transport)
    except _Unreachable as exc:
        return _unreachable("postforme.dev", exc)

    code = _message(resp, "error", "code")
    if code == "err:frontline:client:invalid_key":
        return KeyCheck(INVALID, _scrub(_message(resp, "error", "message"), key)
                        or "The provided API key is invalid.")
    if code == "err:frontline:client:missing_credentials":
        return KeyCheck(UNKNOWN, "postforme.dev saw no credential — key not verified.")

    return _accepted_or_unknown("postforme.dev", resp)


# ── Ask → check → re-ask ────────────────────────────────────────────────────

def resolve_secret(
    check: Callable[[str], KeyCheck],
    value: str,
    ask_again: Callable[[], str],
    report: Callable[[str, str], None],
) -> str:
    """Return a key the service did not reject, re-asking for as long as it does.

    A blank value is returned untouched and never hits the network: three of
    the keys are legitimately optional (`GEMINI_API_KEY` and
    `YOUTUBE_TRANSCRIPT_API_KEY`), so validating "" would just manufacture a
    spurious 401 on most fields. Blank also exits the loop on a *re-*ask,
    which is the deliberate way out for someone who can't produce a working
    key: leave the field unset and let apply_install_config's presence gate
    decide whether that is fatal.

    `check`, `ask_again` and `report` are all injected so this loop is unit-
    testable without a terminal — onboard/tests/test_prompt.py records that
    questionary interaction itself is only ever exercised through a real pty.
    """
    while True:
        # Strip here rather than inside a checker, because this is the value
        # that gets *stored*: trimming only for the probe would verify one
        # string and store a different one.
        value = value.strip()
        if not value:
            return value

        reason = malformed_reason(value)
        if reason:
            report(INVALID, reason)
            value = ask_again()
            continue

        result = check(value)
        report(result.status, result.detail)
        if result.status != INVALID:
            return value
        value = ask_again()
