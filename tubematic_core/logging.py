"""Structured JSONL logging, shared by every Tubematic process.

Each service writes one file per day to a shared directory — `/logs` inside the
containers, `~/.tubematic-data/logs` on the host — named `<service>.<date>.jsonl`.
Flask reads them back at `GET /logs` so the dashboard can show a trail without
being handed the Docker socket.

Three properties are load-bearing and easy to undo by accident:

- **stdout logging is never touched.** `setup_json_logging` only ever *adds* a
  handler. `worker.py` configures `basicConfig(stream=sys.stdout)` and
  `docker compose logs` has to keep working exactly as before.
- **it never raises.** A missing or unwritable log directory degrades to
  stdout-only. Host-side pytest has no `/logs` and cannot create one, and this
  runs at import time, so raising here would take out every test run.
- **secrets are redacted on two axes** — see `redact`.

Yes, this module is called `logging` and imports `logging`. Python 3 imports are
absolute, so the `import logging` below is unambiguously the stdlib.
"""
import json
import logging
import os
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

# The service allowlist. Single source of truth for both halves of the feature:
# a writer names itself from here, and the reader builds filenames from here
# rather than from anything a request supplied.
#
# "poll" is the host-side cron poller (scripts/poll.py). Its older, unstructured
# ~/.tubematic-agent/logs/poll.log is a *different* store and is not managed by
# anything in this module.
SERVICES = ("api", "mcp", "renderer", "poll")

# Ordering for the reader's minimum-level filter. "critical" is included even
# though nothing emits it today: an unknown level must not silently sort below
# "error" and vanish from an error-filtered view.
_LEVEL_RANK = {"debug": 10, "info": 20, "warning": 30, "error": 40, "critical": 50}

# Least to most severe, and the set a caller may filter on. The filter is a
# *minimum*, not an exact match — asking for warnings and being shown warnings
# but not errors would be the wrong way round for the one question anybody asks
# a log viewer.
#
# "critical" is deliberately absent even though _LEVEL_RANK ranks it: nothing
# here emits it, so offering it would put a permanently-empty option in the
# dashboard's filter. It still ranks above "error", so a critical record from
# some third-party logger is returned by an "error" filter rather than hidden.
LEVELS = ("debug", "info", "warning", "error")

# Standard LogRecord attributes, so the formatter can tell a caller's
# extra={"video_id": ...} from the machinery's own fields without an allowlist
# that would need updating every time we want to carry a new one.
_RESERVED = frozenset(vars(logging.LogRecord("", 0, "", 0, "", (), None)).keys()) | {
    "asctime", "message", "taskName",
}

# Fields the reader can filter on. Also what the formatter promotes to the top
# level of the record rather than leaving in the free-form tail.
CONTEXT_FIELDS = ("video_id", "profile_id", "request_id")

_FILENAME_RE = re.compile(r"^(?P<service>[a-z]+)\.(?P<date>\d{4}-\d{2}-\d{2})\.jsonl$")

_REDACTED = "***REDACTED***"

# Terminal colour codes. Werkzeug's startup banner is styled, and a raw escape
# sequence inside a JSON string is unreadable everywhere it is eventually
# displayed — the dashboard, `jq`, a bug report.
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")

# Header- and URL-shaped secrets. These catch a key that was never in our
# settings table — one supplied through the environment, or echoed back by a
# provider. httpx puts the full request URL in its error strings, which is
# exactly how a Gemini key once reached the dashboard-visible comments table.
_PATTERNS = (
    # "xi-api-key: abc", {"x-goog-api-key": "abc"}, Authorization: Bearer abc.
    # Basic is kept with the scheme for the same reason Bearer is: without it the
    # value group stops at the space and redacts the word "Basic", leaving the
    # base64 credential after it in the clear.
    re.compile(r"(?i)\b(xi-api-key|x-goog-api-key|api[-_]?key|authorization)\b"
               r"(\"?\s*[:=]\s*\"?)((?:Bearer|Basic)\s+)?([^\s\"',}&]+)"),
    # Cookie: / Set-Cookie: — a dashboard session cookie is a login. The value
    # is every "; "-joined pair, since one header carries several cookies, and
    # stops at the first space-separated word after them: running to the end
    # of the line instead swallowed whatever else the line said.
    re.compile(r"(?i)(\b(?:set-)?cookie\b\"?\s*[:=]\s*\"?)([^\s;,\"]+(?:;\s*[^\s;,\"]+)*)"),
    # ?key=abc / &access_token=abc in a URL
    re.compile(r"(?i)([?&](?:key|api_key|apikey|token|access_token|refresh_token)=)([^&\s\"']+)"),
    # Provider-shaped literals, for a key that appears with no label at all.
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}"),
    # ElevenLabs keys are sk_ with an underscore, which the OpenAI rule above
    # never matched — outside the services' value axis they went out bare.
    re.compile(r"\bsk_[A-Za-z0-9]{20,}"),
    re.compile(r"\bAIza[A-Za-z0-9_-]{20,}"),
    # OpenAI's 401 body, which needs its own rule because value-matching cannot
    # help: it echoes a *masked slice* of the submitted key
    # ("Incorrect API key provided: bogus-ke*****ev52"), so the literal secret
    # never appears in the text — but twelve real characters of it do. It is the
    # one provider message of the four that carries key material at all.
    re.compile(r"(?i)(incorrect api key provided:\s*)(\S+)"),
    # Discord webhook URLs carry the credential in the *path*, so neither the
    # header rule nor the query-parameter rule above sees it. This needs a
    # pattern rather than value-matching for a structural reason, not a
    # belt-and-braces one: POST /settings probes a webhook URL *before* storing
    # it, so at the moment the request is logged the value is not yet a stored
    # secret and there is nothing for the value axis to match. Observed live —
    # httpx's own "HTTP Request:" line wrote a working token into a log file.
    re.compile(r"(discord(?:app)?\.com/api(?:/v\d{1,2})?/webhooks/\d+/)([A-Za-z0-9_.-]+)"),
)


def redact(text: str, secrets=()) -> str:
    """Strip credentials out of a string before it is written to disk.

    Two axes, because either alone leaves a hole:

    - **patterns** catch a labelled or provider-shaped key we have never seen,
      including one supplied through the environment rather than the settings
      table;
    - **literal values** catch a key that appears bare, with no label and no
      recognisable shape — which is most of them.

    Neither is sufficient on its own, and one known case needs both to miss: a
    provider that echoes a *partial* key back at us defeats value-matching
    outright, because the literal secret never appears in the text. OpenAI's 401
    does exactly that, so it has a pattern of its own.

    Short values are ignored: an empty or near-empty stored credential would
    otherwise match everywhere and redact the whole line into noise.
    """
    if not text:
        return text
    text = _ANSI_RE.sub("", text)
    for secret in secrets:
        if secret and len(secret) >= 8:
            text = text.replace(secret, _REDACTED)
    for pattern in _PATTERNS:
        if pattern.groups == 0:
            text = pattern.sub(_REDACTED, text)
        elif pattern.groups == 2:
            text = pattern.sub(lambda m: m.group(1) + _REDACTED, text)
        else:
            text = pattern.sub(
                lambda m: f"{m.group(1)}{m.group(2)}{m.group(3) or ''}{_REDACTED}", text
            )
    return text


def log_filename(service: str, day: str) -> str:
    """`<service>.<YYYY-MM-DD>.jsonl`. The only place the name is spelled."""
    return f"{service}.{day}.jsonl"


def parse_filename(name: str):
    """-> (service, 'YYYY-MM-DD') or None if the name is not one of ours.

    Returning None rather than raising is what keeps `prune_logs` from deleting
    a file it does not understand.
    """
    m = _FILENAME_RE.match(name)
    return (m.group("service"), m.group("date")) if m else None


def level_rank(level: str) -> int:
    """Rank for the reader's minimum-level filter. Unknown levels rank 0 so a
    record with a level we do not recognise is shown rather than hidden."""
    return _LEVEL_RANK.get((level or "").lower(), 0)


class JsonlFormatter(logging.Formatter):
    """One JSON object per line.

    `ts` is UTC in the same shape `renderer/api/db.py::_now` writes to the
    database — the whole system stores UTC and localises only at display, and a
    second timestamp convention here would be a trap for anyone correlating a
    log line against a row.
    """

    # How long a resolved secret set is reused before the provider is asked
    # again. Keys are rotatable from the dashboard and no setting requires a
    # restart, so a set cached for the life of the process would stop redacting
    # the moment somebody rotated one — the exact situation where a key is most
    # likely to end up in an error string. A minute bounds that window without
    # putting a database read on every log line.
    SECRET_TTL_SECS = 60

    def __init__(self, service: str, secrets=()):
        """`secrets` is either a fixed iterable or a zero-arg callable.

        The callable form is what the services use, so a rotated key starts
        being redacted without a restart. It must never itself log: it is called
        from inside `format`, so a provider that logged its own failure would
        recurse. Every caller wraps its read accordingly.
        """
        super().__init__()
        self.service = service
        self._provider = secrets if callable(secrets) else None
        self._secrets = () if self._provider else tuple(s for s in secrets if s)
        # None means "never fetched", NOT 0.0. time.monotonic() is seconds
        # since boot, so on a freshly-booted machine it is a small number and
        # `now - 0.0 >= SECRET_TTL_SECS` is FALSE -- the provider would never
        # be called and nothing would be redacted for the first minute of the
        # machine's life. That is precisely the window where startup errors
        # (a database that is not up yet, a key that fails validation) get
        # logged. It passed everywhere with real uptime and failed only on a
        # fresh CI runner.
        self._fetched_at = None

    def _resolve_secrets(self):
        if self._provider is None:
            return self._secrets
        now = time.monotonic()
        if self._fetched_at is None or now - self._fetched_at >= self.SECRET_TTL_SECS:
            try:
                self._secrets = tuple(s for s in (self._provider() or ()) if s)
            except Exception:  # noqa: BLE001 - keep the last good set, never raise
                pass
            self._fetched_at = now
        return self._secrets

    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(record.created)),
            "service": self.service,
            "level": record.levelname.lower(),
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["message"] += "\n" + self.formatException(record.exc_info)

        for field in CONTEXT_FIELDS:
            value = getattr(record, field, None)
            if value:
                payload[field] = str(value)

        # Anything else the caller passed in extra={...}, so a new correlation
        # field does not need a change here to survive to disk.
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key not in payload:
                payload[key] = value

        # Redact per field, before serialising. Redacting the finished JSON
        # string instead would miss any secret whose characters get escaped on
        # the way out.
        secrets = self._resolve_secrets()
        payload = {
            k: redact(v, secrets) if isinstance(v, str) else v
            for k, v in payload.items()
        }
        try:
            return json.dumps(payload, default=str)
        except (TypeError, ValueError):
            # A caller put something unserialisable in extra=. Losing the line
            # entirely would be worse than losing its tail.
            return json.dumps({k: payload[k] for k in ("ts", "service", "level", "message")})


class _DropAccessLogs(logging.Filter):
    """Keep Werkzeug's per-request access lines out of the JSONL sink.

    Found by running this against a live stack, and not catchable by the unit
    tests: `app.test_client()` never starts the WSGI server, so Werkzeug's
    access logger is silent under pytest and looks like it does not exist.

    In production it logs every request at INFO to the `werkzeug` logger, which
    propagates to the root logger — where this handler lives. That did two bad
    things. Every request was recorded **twice**, once by this project's
    `after_request` hook (with a request_id, a duration and a video_id) and once
    as a bare access line carrying none of that. And it silently reintroduced
    the `/health` flood the blueprint-scoped hooks were designed to avoid: the
    compose healthcheck runs every 15s, and on a freshly started stack roughly a
    third of all API records were healthcheck noise.

    Only INFO and below are dropped, so a genuine Werkzeug warning or error
    still lands. The deliberate cost: a 404 for a URL matching no route never
    reaches a blueprint hook, so those now appear only on stdout. That is worth
    it against doubling every record the pipeline actually cares about.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        return not (record.name.startswith("werkzeug") and record.levelno <= logging.INFO)


class DailyJsonlHandler(logging.Handler):
    """Appends to `<service>.<today>.jsonl`, rolling over at UTC midnight.

    Written by hand rather than using `TimedRotatingFileHandler`, which names
    its rotations `<base>.<date>` — the live file always carries the bare base
    name, so the reader could not tell today's file from a service named after
    it, and the required `<service>.<date>.jsonl` shape is not expressible.

    Rollover also prunes, which is what makes retention apply on a long-running
    container that is never restarted.
    """

    def __init__(self, service: str, log_dir: Path, retention_days: int):
        super().__init__()
        self.service = service
        self.log_dir = Path(log_dir)
        self.retention_days = retention_days
        self._day = None
        self._stream = None

    def _today(self) -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _ensure_stream(self) -> None:
        day = self._today()
        if self._stream is not None and day == self._day:
            return
        if self._stream is not None:
            try:
                self._stream.close()
            except OSError:
                pass
            self._stream = None
        self._stream = open(self.log_dir / log_filename(self.service, day), "a",
                            encoding="utf-8")
        rolled_over = self._day is not None
        self._day = day
        if rolled_over:
            prune_logs(self.log_dir, self.service, self.retention_days)

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._ensure_stream()
            self._stream.write(self.format(record) + "\n")
            self._stream.flush()
        except Exception:  # noqa: BLE001 - logging must never break its caller
            self.handleError(record)

    def close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.close()
                self._stream = None
        finally:
            super().close()


def prune_logs(log_dir, service: str, retention_days: int) -> int:
    """Delete this service's log files older than `retention_days`. -> count deleted.

    Keys on the **date in the filename**, not mtime: an appended-to file's mtime
    says when it was last written, not which day it covers, so a quiet service
    would keep files forever and a busy one could lose a file it is still using.

    A file whose name does not parse is skipped, never deleted. This directory
    is shared by four services and nothing here should be able to remove
    something it does not recognise.

    Only ever prunes `service`'s own files, so each writer maintains its own and
    a service that is not running cannot have its history deleted by one that is.
    """
    log_dir = Path(log_dir)
    if retention_days < 1:
        return 0
    cutoff = (datetime.now(timezone.utc) - timedelta(days=retention_days)).strftime("%Y-%m-%d")
    deleted = 0
    try:
        names = os.listdir(log_dir)
    except OSError:
        return 0
    for name in names:
        parsed = parse_filename(name)
        if parsed is None or parsed[0] != service:
            continue
        if parsed[1] < cutoff:  # ISO dates compare correctly as strings
            try:
                (log_dir / name).unlink()
                deleted += 1
            except OSError:
                pass
    return deleted


def _preserve_werkzeug_stdout() -> None:
    """Give Werkzeug back the stdout handler that adding ours takes away.

    Werkzeug installs its own StreamHandler lazily, and only when
    `_has_level_handler` finds no handler anywhere up the chain — root included.
    Adding a root handler therefore makes it stop installing one, so its request
    log silently stops reaching stdout. That is a regression in
    `docker compose logs` caused purely by switching structured logging on, and
    it is invisible under pytest because the test client never starts the server.

    Verified against a live stack: `_has_level_handler(werkzeug)` is False before
    `setup_json_logging` and True after.

    Giving Werkzeug an explicit handler restores the previous stdout behaviour
    and leaves propagation alone, so `_DropAccessLogs` still keeps the noisy
    duplicate out of the JSONL file while genuine Werkzeug warnings still land
    in both places.
    """
    wz = logging.getLogger("werkzeug")
    if not wz.handlers:
        wz.addHandler(logging.StreamHandler())


def setup_json_logging(service: str, log_dir, retention_days: int = 14,
                       secrets=(), level=logging.INFO):
    """Add a JSONL file handler to the root logger. -> the handler, or None.

    Returns None — quietly, having changed nothing — when `service` is not in
    SERVICES or the directory cannot be written. The caller is expected to carry
    on with stdout logging; see the module docstring for why this must not raise.

    Existing handlers are left alone. Calling this twice for the same service
    replaces the previous handler rather than doubling every line.
    """
    if service not in SERVICES:
        return None
    try:
        log_dir = Path(log_dir)
        log_dir.mkdir(parents=True, exist_ok=True)
        # Probe rather than trusting the mkdir: the directory routinely exists
        # already and is root-owned, which os.access alone would not settle.
        probe = log_dir / f".{service}.write-test"
        with open(probe, "a"):
            pass
        probe.unlink(missing_ok=True)
    except OSError:
        return None

    root = logging.getLogger()
    for existing in list(root.handlers):
        if isinstance(existing, DailyJsonlHandler) and existing.service == service:
            root.removeHandler(existing)
            existing.close()

    _preserve_werkzeug_stdout()

    handler = DailyJsonlHandler(service, log_dir, retention_days)
    handler.setFormatter(JsonlFormatter(service, secrets))
    handler.addFilter(_DropAccessLogs())
    handler.setLevel(level)
    root.addHandler(handler)
    if root.level > level or root.level == logging.NOTSET:
        root.setLevel(level)

    prune_logs(log_dir, service, retention_days)
    return handler


# ── Reading ──────────────────────────────────────────────────────────────────

def read_logs(log_dir, services=None, min_level=None, video_id=None,
              profile_id=None, search=None, limit=200) -> list:
    """Newest-first records matching the filters. Never raises on bad input data.

    `services` is resolved against SERVICES by the caller, never taken from a
    request verbatim — filenames here are built, not received. Passing None
    reads all four, which is what a `video_id` query needs: one video's trail
    spans the renderer that rendered it, the MCP tools that voiced and staged
    it, and the API calls that moved it between statuses.

    Scans each service's files newest day first and stops as soon as it has
    `limit` matches for that service, so the cost is bounded by what is returned
    rather than by how much history is retained. Malformed lines are skipped —
    a half-written final line is normal in a file being appended to, and one
    bad line must not blank the whole view.
    """
    log_dir = Path(log_dir)
    wanted = tuple(services) if services else SERVICES
    floor = level_rank(min_level) if min_level else 0
    needle = (search or "").lower()

    try:
        names = os.listdir(log_dir)
    except OSError:
        return []

    by_service = {}
    for name in names:
        parsed = parse_filename(name)
        if parsed and parsed[0] in wanted:
            by_service.setdefault(parsed[0], []).append((parsed[1], name))

    collected = []
    for service, files in by_service.items():
        found = []
        for _day, name in sorted(files, reverse=True):
            try:
                with open(log_dir / name, encoding="utf-8", errors="replace") as fh:
                    lines = fh.readlines()
            except OSError:
                continue
            for line in reversed(lines):  # within a file, newest is last
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(rec, dict):
                    continue
                if floor and level_rank(rec.get("level")) < floor:
                    continue
                if video_id and rec.get("video_id") != video_id:
                    continue
                if profile_id and rec.get("profile_id") != profile_id:
                    continue
                if needle and needle not in json.dumps(rec, default=str).lower():
                    continue
                found.append(rec)
                if len(found) >= limit:
                    break
            if len(found) >= limit:
                break
        collected.extend(found)

    # Merge the per-service runs. Sorting the whole collection is fine because
    # each run is already capped at `limit`, so this is bounded by
    # limit * len(SERVICES), not by the size of the log directory.
    collected.sort(key=lambda r: r.get("ts") or "", reverse=True)
    return collected[:limit]
