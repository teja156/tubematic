"""Tests for the shared JSONL logging module.

Deliberately no __init__.py in this directory. Three of the repo's suites
(renderer/api/tests, onboard/tests, scripts/tests) each have one and therefore
all claim the top-level package name `tests`, which is why they cannot be
collected in a single pytest invocation. mcp/tests and vqa/tests stay clear of
that by having none; this suite does the same.
"""
import json
import logging
import os
import sqlite3
import stat
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from tubematic_core.logging import (  # noqa: E402
    LEVELS,
    SERVICES,
    DailyJsonlHandler,
    JsonlFormatter,
    log_filename,
    parse_filename,
    prune_logs,
    read_logs,
    redact,
    setup_json_logging,
)


# root ignores the permission bits these two tests rely on, so they would pass
# vacuously rather than failing loudly. Tests do run as root in a container.
needs_unprivileged = pytest.mark.skipif(
    os.geteuid() == 0, reason="root bypasses the directory permissions under test"
)


def _day(offset: int = 0) -> str:
    return (datetime.now(timezone.utc) + timedelta(days=offset)).strftime("%Y-%m-%d")


def _write(log_dir: Path, service: str, records, day=None):
    path = log_dir / log_filename(service, day or _day())
    with open(path, "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec) + "\n")
    return path


def _record(msg="hello", level=logging.INFO, **extra) -> logging.LogRecord:
    rec = logging.LogRecord("t", level, __file__, 1, msg, (), None)
    for k, v in extra.items():
        setattr(rec, k, v)
    return rec


@pytest.fixture(autouse=True)
def _clean_root_handlers():
    """Every test starts and ends with the root logger as it found it.

    setup_json_logging mutates the root logger by design, so without this a
    failing test leaks a handler into every test that follows it.
    """
    root = logging.getLogger()
    before, level = list(root.handlers), root.level
    yield
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            h.close()
    for h in before:
        if h not in root.handlers:
            root.addHandler(h)
    root.setLevel(level)


# ── Formatter ────────────────────────────────────────────────────────────────

def test_emits_one_json_object_with_the_required_fields():
    out = json.loads(JsonlFormatter("renderer").format(_record("render complete")))
    assert out["service"] == "renderer"
    assert out["level"] == "info"
    assert out["message"] == "render complete"
    # UTC, matching renderer/api/db.py::_now — not a local or offset-bearing time.
    assert out["ts"].endswith("Z")
    datetime.strptime(out["ts"], "%Y-%m-%dT%H:%M:%SZ")


def test_context_fields_are_promoted_when_given_and_absent_when_not():
    with_ctx = json.loads(
        JsonlFormatter("mcp").format(_record(video_id="vid_abc", request_id="r1"))
    )
    assert with_ctx["video_id"] == "vid_abc"
    assert with_ctx["request_id"] == "r1"
    # Omitted, not null: a reader filtering on video_id must not match a record
    # that simply had none.
    assert "profile_id" not in with_ctx
    assert "video_id" not in json.loads(JsonlFormatter("mcp").format(_record()))


def test_an_unserialisable_extra_still_produces_a_usable_line():
    """Losing the tail beats losing the record."""
    out = json.loads(JsonlFormatter("api").format(_record("boom", blob=object())))
    assert out["message"] == "boom"
    assert out["level"] == "info"


def test_exception_text_is_carried_into_the_message():
    try:
        raise ValueError("kaboom")
    except ValueError:
        rec = logging.LogRecord("t", logging.ERROR, __file__, 1, "failed", (), sys.exc_info())
    out = json.loads(JsonlFormatter("api").format(rec))
    assert "kaboom" in out["message"] and "Traceback" in out["message"]


# ── Redaction ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "xi-api-key: xi_live_9f8e7d6c5b4a3210",
    'headers={"x-goog-api-key": "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6"}',
    "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6",
    "GET https://api/x?key=AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6 -> 400",
    "auth failed for sk-proj-A1B2C3D4E5F6G7H8I9J0",
    # OpenAI is the one provider that echoes real key characters back. Value
    # matching cannot catch this — the literal key is not in the string.
    "Incorrect API key provided: sk-live-*****ev52",
])
def test_pattern_axis_redacts_labelled_and_provider_shaped_keys(text):
    out = redact(text)
    assert "***REDACTED***" in out
    for leak in ("xi_live_9f8e7d6c5b4a3210", "AIzaSyA1B2C3D4E5F6G7H8I9J0K1L2M3N4O5P6",
                 "eyJhbGciOiJIUzI1NiIsInR5cCI6", "sk-proj-A1B2C3D4E5F6G7H8I9J0",
                 "sk-live-*****ev52"):
        assert leak not in out


@pytest.mark.parametrize("text, leak, kept", [
    # ElevenLabs keys use an underscore; the sk- rule never matched them.
    ("voice failed for sk_0123456789abcdef0123456789abcdef0123456789abcdef",
     "0123456789abcdef0123456789abcdef", "voice failed for"),
    # Before, the value group stopped at the space after "Basic" and the
    # base64 credential went out in the clear.
    ("Authorization: Basic dXNlcjpodW50ZXIyLXBhc3N3b3Jk", "dXNlcjpodW50ZXIy", "Authorization: Basic "),
    ('{"authorization": "Basic dXNlcjpodW50ZXIyLXBhc3N3b3Jk"}', "dXNlcjpodW50ZXIy", "Basic "),
    # A dashboard session cookie is a login.
    ("Cookie: tm_session=eyJ1aWQiOjF9.Zx9; theme=dark", "eyJ1aWQiOjF9", "Cookie: "),
    ("set-cookie: tm_session=eyJ1aWQiOjF9.Zx9; HttpOnly; Path=/", "eyJ1aWQiOjF9", "set-cookie: "),
    ('{"Cookie": "tm_session=eyJ1aWQiOjF9.Zx9"}', "eyJ1aWQiOjF9", '"Cookie": "'),
])
def test_elevenlabs_keys_basic_auth_and_cookies_are_redacted(text, leak, kept):
    out = redact(text)
    assert leak not in out
    assert kept in out, "the label should survive so the line stays readable"


def test_the_cookie_rule_stops_at_the_end_of_the_cookie():
    """Seen live: running to the end of the line erased everything after it."""
    out = redact("Cookie: tm_session=abc123def456; theme=dark | then the error: boom")
    assert "abc123def456" not in out and "theme=dark" not in out
    assert out.endswith("| then the error: boom")


def test_the_cookie_rule_needs_a_header_shape_not_just_the_word():
    assert redact("cookie consent banner dismissed") == "cookie consent banner dismissed"


def test_a_discord_webhook_token_is_redacted_from_the_path():
    """The credential is in the URL *path*, so neither the header rule nor the
    query-parameter rule sees it.

    This needs the pattern axis for a structural reason, not as belt and braces:
    POST /settings probes a webhook URL before storing it, so when httpx logs
    the request there is no stored secret for the value axis to match. Observed
    live — a working token reached a JSONL log file exactly this way.
    """
    token = "fakeWebhookToken_NOT-REAL_0123456789abcdefghijklmnopqrstuvwxyz.ABCDEF"
    out = redact(f'HTTP Request: GET https://discord.com/api/webhooks/123456789012345678/{token} "HTTP/1.1 200 OK"')
    assert token not in out
    assert "123456789012345678" in out, "the webhook should stay identifiable"


def test_the_webhook_rule_does_not_eat_an_ordinary_discord_link():
    """It must key on the webhook path, not merely on the hostname."""
    out = redact("see https://discord.com/channels/123/456 for context")
    assert "discord.com/channels/123/456" in out


def test_value_axis_redacts_a_bare_key_with_no_label_or_recognisable_shape():
    """The pattern axis cannot help here, which is why both axes exist."""
    secret = "abcd1234efgh5678"
    assert secret not in redact(f"upstream said no ({secret})", [secret])


def test_a_short_secret_is_ignored_rather_than_redacting_the_whole_line():
    """An unset or near-empty stored credential must not match everywhere."""
    assert redact("nothing to see here", ["", "abc"]) == "nothing to see here"


def test_the_formatter_redacts_before_writing_not_at_a_display_boundary():
    secret = "xi_key_abcdef123456"
    line = JsonlFormatter("mcp", [secret]).format(_record(f"voice failed: {secret}"))
    assert secret not in line
    assert json.loads(line)["message"].endswith("***REDACTED***")


# ── Filenames and pruning ────────────────────────────────────────────────────

def test_parse_filename_round_trips_and_rejects_anything_else():
    assert parse_filename(log_filename("api", "2026-09-06")) == ("api", "2026-09-06")
    for bad in ("api.jsonl", "api.2026-9-6.jsonl", "notes.txt", "api.2026-09-06.jsonl.bak",
                "../../etc/passwd"):
        assert parse_filename(bad) is None


def test_prune_deletes_past_the_cutoff_and_keeps_what_is_inside_it(tmp_path):
    old = _write(tmp_path, "api", [{"m": 1}], day=_day(-30))
    recent = _write(tmp_path, "api", [{"m": 2}], day=_day(-1))
    assert prune_logs(tmp_path, "api", 14) == 1
    assert not old.exists() and recent.exists()


def test_prune_only_touches_its_own_service(tmp_path):
    """Four services share this directory; a writer maintains only its own."""
    mine = _write(tmp_path, "api", [{"m": 1}], day=_day(-30))
    theirs = _write(tmp_path, "renderer", [{"m": 1}], day=_day(-30))
    prune_logs(tmp_path, "api", 14)
    assert not mine.exists() and theirs.exists()


def test_prune_skips_a_file_whose_name_it_does_not_understand(tmp_path):
    """Never delete something unrecognised out of a shared directory."""
    stray = tmp_path / "important-notes.txt"
    stray.write_text("keep me")
    os.utime(stray, (0, 0))  # ancient by mtime, but not one of ours by name
    prune_logs(tmp_path, "api", 1)
    assert stray.exists()


def test_prune_on_a_missing_directory_is_a_no_op(tmp_path):
    assert prune_logs(tmp_path / "nope", "api", 14) == 0


# ── setup_json_logging: degradation ──────────────────────────────────────────

def test_setup_adds_a_handler_without_disturbing_existing_ones(tmp_path):
    """The acceptance criterion 'existing stdout logs still work' lives here."""
    root = logging.getLogger()
    stdout_handler = logging.StreamHandler(sys.stdout)
    root.addHandler(stdout_handler)
    try:
        assert setup_json_logging("api", tmp_path) is not None
        assert stdout_handler in root.handlers
        assert sum(isinstance(h, DailyJsonlHandler) for h in root.handlers) == 1
    finally:
        root.removeHandler(stdout_handler)


@needs_unprivileged
def test_setup_on_a_missing_uncreatable_directory_returns_none_and_does_not_raise(tmp_path):
    """Host-side pytest has no /logs and cannot create one, and this runs at
    import time — raising here would take out every test run in the repo."""
    blocked = tmp_path / "ro"
    blocked.mkdir()
    blocked.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        assert setup_json_logging("api", blocked / "logs") is None
        assert not any(isinstance(h, DailyJsonlHandler) for h in logging.getLogger().handlers)
    finally:
        blocked.chmod(stat.S_IRWXU)


@needs_unprivileged
def test_setup_on_an_existing_unwritable_directory_returns_none(tmp_path):
    """mkdir succeeding does not mean the directory can be written — the shared
    mount routinely exists already and is root-owned."""
    d = tmp_path / "logs"
    d.mkdir()
    d.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        assert setup_json_logging("renderer", d) is None
    finally:
        d.chmod(stat.S_IRWXU)


def test_setup_rejects_a_service_outside_the_allowlist(tmp_path):
    assert setup_json_logging("../../etc", tmp_path) is None
    assert setup_json_logging("dashboard", tmp_path) is None


def test_calling_setup_twice_replaces_rather_than_doubling(tmp_path):
    setup_json_logging("api", tmp_path)
    setup_json_logging("api", tmp_path)
    root = logging.getLogger()
    assert sum(isinstance(h, DailyJsonlHandler) for h in root.handlers) == 1
    logging.getLogger("x").info("once")
    assert len(read_logs(tmp_path)) == 1


def test_a_logged_line_lands_in_todays_file_and_round_trips(tmp_path):
    setup_json_logging("renderer", tmp_path)
    logging.getLogger("worker").info("[vid_1] render complete", extra={"video_id": "vid_1"})
    assert (tmp_path / log_filename("renderer", _day())).exists()
    (rec,) = read_logs(tmp_path)
    assert rec["message"] == "[vid_1] render complete"
    assert rec["video_id"] == "vid_1"
    assert rec["service"] == "renderer"


def test_setup_prunes_expired_files_on_startup(tmp_path):
    old = _write(tmp_path, "api", [{"m": 1}], day=_day(-40))
    setup_json_logging("api", tmp_path, retention_days=14)
    assert not old.exists()


def test_rollover_writes_a_new_file_and_prunes(tmp_path):
    """Retention has to apply on a container that runs for months without a
    restart, so the daily rollover prunes too."""
    handler = DailyJsonlHandler("api", tmp_path, retention_days=14)
    handler.setFormatter(JsonlFormatter("api"))
    expired = _write(tmp_path, "api", [{"m": 1}], day=_day(-40))
    handler.emit(_record("first"))
    assert expired.exists(), "startup pruning is setup's job, not the handler's"

    handler._day = _day(-1)  # pretend the process has been up since yesterday
    handler.emit(_record("second"))
    assert (tmp_path / log_filename("api", _day())).exists()
    assert not expired.exists()
    handler.close()


# ── Reading ──────────────────────────────────────────────────────────────────

def test_read_returns_newest_first(tmp_path):
    _write(tmp_path, "api", [
        {"ts": "2026-09-01T00:00:00Z", "service": "api", "level": "info", "message": "old"},
        {"ts": "2026-09-03T00:00:00Z", "service": "api", "level": "info", "message": "new"},
    ])
    assert [r["message"] for r in read_logs(tmp_path)] == ["new", "old"]


def test_level_filter_is_a_minimum_not_an_exact_match(tmp_path):
    _write(tmp_path, "api", [
        {"ts": "2026-09-01T00:00:00Z", "level": "debug", "message": "d"},
        {"ts": "2026-09-02T00:00:00Z", "level": "info", "message": "i"},
        {"ts": "2026-09-03T00:00:00Z", "level": "warning", "message": "w"},
        {"ts": "2026-09-04T00:00:00Z", "level": "error", "message": "e"},
    ])
    assert {r["message"] for r in read_logs(tmp_path, min_level="warning")} == {"w", "e"}
    assert {r["message"] for r in read_logs(tmp_path, min_level="error")} == {"e"}


def test_reading_with_no_service_spans_all_of_them(tmp_path):
    """A video's trail is cross-service by construction: the renderer renders
    it, MCP voices and stages it, the API moves it between statuses."""
    for svc in ("api", "mcp", "renderer"):
        _write(tmp_path, svc, [
            {"ts": f"2026-09-0{SERVICES.index(svc) + 1}T00:00:00Z",
             "service": svc, "level": "info", "message": svc, "video_id": "vid_1"},
        ])
    assert {r["service"] for r in read_logs(tmp_path, video_id="vid_1")} == {"api", "mcp", "renderer"}


def test_video_and_profile_filters_exclude_records_that_carry_neither(tmp_path):
    _write(tmp_path, "api", [
        {"ts": "2026-09-01T00:00:00Z", "level": "info", "message": "a", "video_id": "vid_1"},
        {"ts": "2026-09-02T00:00:00Z", "level": "info", "message": "b", "video_id": "vid_2"},
        {"ts": "2026-09-03T00:00:00Z", "level": "info", "message": "c"},
    ])
    assert [r["message"] for r in read_logs(tmp_path, video_id="vid_1")] == ["a"]
    assert read_logs(tmp_path, profile_id="p1") == []


def test_search_matches_anywhere_in_the_record(tmp_path):
    _write(tmp_path, "api", [
        {"ts": "2026-09-01T00:00:00Z", "level": "info", "message": "render TIMED OUT"},
        {"ts": "2026-09-02T00:00:00Z", "level": "info", "message": "all good"},
    ])
    assert [r["message"] for r in read_logs(tmp_path, search="timed out")] == ["render TIMED OUT"]


def test_limit_caps_the_result_and_keeps_the_newest(tmp_path):
    _write(tmp_path, "api", [
        {"ts": f"2026-09-{d:02d}T00:00:00Z", "level": "info", "message": str(d)}
        for d in range(1, 11)
    ])
    assert [r["message"] for r in read_logs(tmp_path, limit=3)] == ["10", "9", "8"]


def test_malformed_lines_are_skipped_rather_than_blanking_the_view(tmp_path):
    """A half-written final line is normal in a file being appended to."""
    path = tmp_path / log_filename("api", _day())
    path.write_text(
        '{"ts": "2026-09-01T00:00:00Z", "level": "info", "message": "good"}\n'
        "not json at all\n"
        '["a list, not an object"]\n'
        '{"ts": "2026-09-02T00:00:00Z", "level": "info", "mess\n'
    )
    assert [r["message"] for r in read_logs(tmp_path)] == ["good"]


def test_reading_a_missing_directory_returns_empty(tmp_path):
    assert read_logs(tmp_path / "nope") == []


def test_reader_only_opens_files_matching_the_naming_scheme(tmp_path):
    """The reader builds filenames from the allowlist; nothing else is opened."""
    (tmp_path / "secrets.txt").write_text('{"ts": "2026-09-01T00:00:00Z", "message": "leak"}\n')
    (tmp_path / "dashboard.2026-09-01.jsonl").write_text(
        '{"ts": "2026-09-01T00:00:00Z", "message": "not a known service"}\n'
    )
    assert read_logs(tmp_path) == []


def test_a_callable_secret_provider_picks_up_a_rotated_key(monkeypatch):
    """Keys are rotatable from the dashboard and no setting requires a restart.
    A set cached for the life of the process would stop redacting exactly when
    a key is most likely to surface in an error string."""
    current = {"key": "old_secret_value_1"}
    fmt = JsonlFormatter("api", lambda: [current["key"]])

    assert "old_secret_value_1" not in fmt.format(_record("boom old_secret_value_1"))

    current["key"] = "new_secret_value_2"
    # Still inside the TTL, so the old set is deliberately still in force.
    assert "new_secret_value_2" in fmt.format(_record("boom new_secret_value_2"))

    fmt._fetched_at -= JsonlFormatter.SECRET_TTL_SECS + 1
    assert "new_secret_value_2" not in fmt.format(_record("boom new_secret_value_2"))


def test_secrets_are_redacted_on_a_freshly_booted_machine(monkeypatch):
    """time.monotonic() is seconds since BOOT, so it is a small number on a
    machine that just started. Using 0.0 as the "never fetched" marker made
    `now - _fetched_at >= TTL` false for the first SECRET_TTL_SECS of uptime,
    so the provider was never called and NOTHING was redacted -- during exactly
    the window when startup failures are being logged.

    Every machine with real uptime hides this, which is why it survived: it
    reproduces only where monotonic() is still below the TTL. Pinned with an
    explicit small clock rather than by hoping for a fresh runner.
    """
    monkeypatch.setattr(time, "monotonic", lambda: 12.5)
    fmt = JsonlFormatter("api", lambda: ["boot_window_secret"])
    assert "boot_window_secret" not in fmt.format(_record("boom boot_window_secret"))


def test_a_failing_secret_provider_keeps_the_last_good_set_and_never_raises():
    """The provider reads the database, and the thing being logged is quite
    often a database error. It must not be able to take logging down."""
    state = {"fail": False}

    def provider():
        if state["fail"]:
            raise sqlite3.OperationalError("database is locked")
        return ["secret_value_abc"]

    fmt = JsonlFormatter("api", provider)
    assert "secret_value_abc" not in fmt.format(_record("a secret_value_abc"))

    state["fail"] = True
    fmt._fetched_at -= JsonlFormatter.SECRET_TTL_SECS + 1
    out = fmt.format(_record("b secret_value_abc"))
    assert "secret_value_abc" not in out


def test_merging_across_services_returns_the_globally_newest_not_a_share_of_each(tmp_path):
    """A chatty service must not crowd out a quiet one's newer records.

    Each service is scanned and capped independently, so the merge has to happen
    before the final truncation — otherwise the answer is a plausible-looking
    list that is quietly missing entries.
    """
    # `api` is noisy but old; `renderer` is quiet but recent.
    _write(tmp_path, "api", [
        {"ts": f"2026-09-01T{h // 60:02d}:{h % 60:02d}:00Z", "service": "api",
         "level": "info", "message": f"api-{h}"}
        for h in range(300)
    ])
    _write(tmp_path, "renderer", [
        {"ts": f"2026-09-05T00:0{i}:00Z", "service": "renderer",
         "level": "info", "message": f"renderer-{i}"}
        for i in range(5)
    ])

    got = read_logs(tmp_path, limit=10)
    assert len(got) == 10
    # Every renderer record is newer than every api record, so all five must be
    # present and must lead.
    assert [r["message"] for r in got[:5]] == [f"renderer-{i}" for i in (4, 3, 2, 1, 0)]
    assert all(r["service"] == "api" for r in got[5:])


def test_a_quiet_service_is_not_lost_behind_a_service_that_fills_the_limit(tmp_path):
    """The inverse: one service alone can supply more than `limit` records."""
    _write(tmp_path, "api", [
        {"ts": f"2026-09-06T00:{m:02d}:00Z", "service": "api",
         "level": "info", "message": f"api-{m}"}
        for m in range(60)
    ])
    _write(tmp_path, "poll", [
        {"ts": "2026-09-06T23:00:00Z", "service": "poll",
         "level": "info", "message": "poll-newest"},
    ])
    got = read_logs(tmp_path, limit=5)
    assert got[0]["message"] == "poll-newest"
    assert len(got) == 5


def test_critical_is_filterable_via_error_rather_than_being_its_own_option(tmp_path):
    """Nothing emits critical, so offering it would be a permanently-empty
    dropdown option — but a third-party logger's critical record must not be
    hidden from the one filter people actually use."""
    assert "critical" not in LEVELS
    _write(tmp_path, "api", [
        {"ts": "2026-09-06T01:00:00Z", "level": "critical", "message": "c"},
        {"ts": "2026-09-06T00:00:00Z", "level": "info", "message": "i"},
    ])
    assert [r["message"] for r in read_logs(tmp_path, min_level="error")] == ["c"]


# ── Werkzeug access logs (found against a live stack) ────────────────────────

def test_werkzeug_access_lines_are_kept_out_of_the_file(tmp_path):
    """Werkzeug logs every request at INFO to a logger that propagates to root.

    Unit tests could not see this: `app.test_client()` never starts the WSGI
    server, so under pytest the access logger is silent. On a live stack it
    duplicated every request and reintroduced the /health flood that scoping the
    hooks to the blueprint was meant to prevent.
    """
    setup_json_logging("api", tmp_path)
    logging.getLogger("werkzeug").info(
        '127.0.0.1 - - [10/Sep/2026 10:07:18] "GET /health HTTP/1.1" 200 -')
    logging.getLogger("api").info("GET /stats -> 200")

    messages = [r["message"] for r in read_logs(tmp_path)]
    assert messages == ["GET /stats -> 200"]


def test_a_real_werkzeug_warning_still_lands(tmp_path):
    """Only the per-request noise is dropped, not the logger."""
    setup_json_logging("api", tmp_path)
    logging.getLogger("werkzeug").warning("address already in use")
    assert [r["message"] for r in read_logs(tmp_path)] == ["address already in use"]


def test_ansi_escapes_are_stripped(tmp_path):
    """Werkzeug's startup banner is colourised, and a raw escape sequence inside
    a JSON string is unreadable in the dashboard, in jq and in a bug report."""
    setup_json_logging("api", tmp_path)
    logging.getLogger("api").warning("\x1b[31m\x1b[1mWARNING: dev server\x1b[0m")
    (rec,) = read_logs(tmp_path)
    assert rec["message"] == "WARNING: dev server"
    assert "\x1b" not in rec["message"]


def test_setup_does_not_silently_take_werkzeug_off_stdout(tmp_path):
    """Adding a root handler stops Werkzeug installing its own, which silently
    removes Flask's request log from `docker compose logs`. Found live; the test
    client never starts the server, so pytest cannot see it happen naturally."""
    # No _has_level_handler precondition here: pytest's own logging plugin
    # holds a root handler for the whole session, so the "nothing handles
    # werkzeug yet" state cannot be reproduced under the test runner. That is
    # precisely why this had to be found on a live stack. What is assertable is
    # the remedy — after setup, werkzeug owns a handler regardless of root.
    wz = logging.getLogger("werkzeug")
    saved = list(wz.handlers)
    for h in saved:
        wz.removeHandler(h)
    try:
        setup_json_logging("api", tmp_path)
        assert wz.handlers, "werkzeug must keep a stdout handler of its own"
        assert any(isinstance(h, logging.StreamHandler) for h in wz.handlers)
    finally:
        for h in list(wz.handlers):
            wz.removeHandler(h)
        for h in saved:
            wz.addHandler(h)
