"""Renderers: the rules shared by the render gateway, the worker, the API and the MCP server.

A renderer is a machine that renders videos. The built-in one runs beside the
API; remote ones run on other hosts. None of them reads the database: each
calls the API's render gateway over HTTPS, and every decision about who may
call, which video a caller gets and whether "the GPU" works lives here, so the
gateway, the worker's sweeps, the API's GPU gates and the MCP server all read
one definition.

Free of Flask and of network I/O: functions take an sqlite3 connection (any
row_factory) and return plain data. A function that writes never commits; the
caller owns the transaction, exactly like the rest of the API's helpers.
Every timestamp is the database's UTC "%Y-%m-%dT%H:%M:%SZ" string; a `now`
argument may be that string or an aware datetime.
"""
import base64
import binascii
import hashlib
import hmac
import json
import re
import secrets
import statistics
from datetime import datetime, timedelta, timezone

BUILTIN_ID = "builtin"
BUILTIN_NAME = "Built-in renderer"

ONLINE_SECS = 120          # a renderer heartbeats every HEARTBEAT_SECS; four missed beats is offline
HEARTBEAT_SECS = 30
LEASE_SECS = 300           # a claim holds its video this long; every heartbeat extends it
CREDENTIAL_DAYS = 30
ROTATE_AFTER_DAYS = 15
ENROLLMENT_SECS = 3600
GPU_WAIT_SECS = 1800
STARVATION_SECS = 600
FINISH_TOLERANCE = 1.25
TOKEN_PREFIX = "tmr1."

KINDS = ("dom", "cartoon_3d", "mascot")
TIMINGS_WINDOW = 5
# Priors for a renderer with no timings of a kind yet: measured on the GTX 1650
# (~0.2 s/frame) and on a 6-core CPU in software WebGL (~1 s/frame), rounded
# pessimistic. A CPU's prior scales with its core count around a 4-core machine.
GPU_PRIOR_SECS_PER_FRAME = 0.25
CPU_PRIOR_SECS_PER_FRAME = 1.5
CPU_PRIOR_REFERENCE_CPUS = 4
# A queued video whose frame count the caller could not read is weighed as a
# 90-second Short at 30 fps, so a busy renderer's head start is compared with a
# realistic job rather than a zero-length one (which would always look fastest).
DEFAULT_FRAMES = 2700

TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
CREDENTIAL_EXPIRED_ERROR = "credential expired — re-enroll"

_PIN = re.compile(r"^sha256:[0-9a-f]{64}$")


class CredentialExpired(Exception):
    """A remote renderer presented a credential past its expiry.

    An exception rather than a None return, on purpose: the gateway must answer
    401 {"error": "credential_expired"} (not the generic 401), and a caller that
    forgets to handle this fails closed with a 500 instead of authenticating.
    authenticate() has already written the renderer's last_error; the caller
    commits that before answering.
    """

    def __init__(self, renderer_id: str):
        super().__init__(f"renderer {renderer_id}: {CREDENTIAL_EXPIRED_ERROR}")
        self.renderer_id = renderer_id


class EnrollmentInvalid(ValueError):
    """An enrollment secret that is unknown, already used or expired. One error
    for all three, so a caller learns nothing about which secrets exist."""


# ── time ──────────────────────────────────────────────────────────────────────

def now_ts() -> str:
    return datetime.now(timezone.utc).strftime(TS_FORMAT)


def parse_ts(value) -> datetime | None:
    """A DB timestamp (or an aware datetime) as an aware UTC datetime; None for
    '' / None / anything unparseable. Never raises."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if not value:
        return None
    try:
        return datetime.strptime(str(value), TS_FORMAT).replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _now_dt(now) -> datetime:
    dt = parse_ts(now) if now is not None else None
    return dt or datetime.now(timezone.utc)


def ts_add(now, secs: float) -> str:
    return (_now_dt(now) + timedelta(seconds=secs)).strftime(TS_FORMAT)


def age_secs(ts, now) -> float | None:
    """Seconds from `ts` to `now`, or None when `ts` is empty or unparseable."""
    then = parse_ts(ts)
    return None if then is None else (_now_dt(now) - then).total_seconds()


# ── secrets, pins and enrollment tokens ───────────────────────────────────────

def hash_secret(s: str) -> str:
    """sha256 hex. Credentials and enrollment secrets are 256-bit random, so a
    plain hash is enough (no salt or slow hash: there is nothing to guess)."""
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def new_secret() -> str:
    return secrets.token_urlsafe(32)


def cert_pin(der: bytes) -> str:
    """The pin of the gateway's certificate: sha256 of the certificate DER, not
    of its public key. A stdlib-only client can compute it
    (ssl.PEM_cert_to_DER_cert), which an SPKI pin would need a parser for."""
    return "sha256:" + hashlib.sha256(der).hexdigest()


def encode_enrollment_token(url: str, secret: str, pin: str) -> str:
    payload = json.dumps({"u": url, "s": secret, "p": pin}, separators=(",", ":"))
    return TOKEN_PREFIX + base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decode_enrollment_token(tok) -> dict:
    """{"url", "secret", "pin"} from a token. ValueError on anything malformed:
    wrong prefix, bad base64 or JSON, a missing or empty field, a gateway URL
    that is not https, or a pin that is not "sha256:<64 hex>"."""
    if not isinstance(tok, str):
        raise ValueError("the enrollment token is not a string")
    tok = tok.strip()
    if not tok.startswith(TOKEN_PREFIX):
        raise ValueError(f"the enrollment token does not start with {TOKEN_PREFIX!r}")
    body = tok[len(TOKEN_PREFIX):]
    try:
        raw = base64.urlsafe_b64decode(body + "=" * (-len(body) % 4))
        data = json.loads(raw.decode("utf-8"))
    except (binascii.Error, ValueError, UnicodeDecodeError):
        raise ValueError("the enrollment token is damaged (it was probably cut off when copied)") from None
    if not isinstance(data, dict):
        raise ValueError("the enrollment token is damaged")
    url, secret, pin = data.get("u"), data.get("s"), data.get("p")
    if not all(isinstance(v, str) and v for v in (url, secret, pin)):
        raise ValueError("the enrollment token is missing a field")
    if not url.startswith("https://"):
        raise ValueError("the enrollment token's gateway address is not https")
    if not _PIN.match(pin):
        raise ValueError("the enrollment token's certificate pin is malformed")
    return {"url": url, "secret": secret, "pin": pin}


def create_enrollment(con, name: str = "", now=None) -> tuple[str, str]:
    """A new one-time enrollment secret, valid for ENROLLMENT_SECS. Only its
    hash is stored. Returns (secret, expires_at)."""
    secret = new_secret()
    created = _now_dt(now).strftime(TS_FORMAT)
    expires = ts_add(now, ENROLLMENT_SECS)
    con.execute("INSERT INTO renderer_enrollments (secret_hash, name, created_at, expires_at) "
                "VALUES (?, ?, ?, ?)", (hash_secret(secret), name or "", created, expires))
    return secret, expires


# ── rows ──────────────────────────────────────────────────────────────────────

def _get(row, key, default=None):
    try:
        value = row[key]
    except (KeyError, IndexError, TypeError):
        return default
    return default if value is None else value


def _dicts(cur) -> list[dict]:
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _renderer_rows(con) -> list[dict]:
    """Every renderer not removed, the built-in first, then by name."""
    return _dicts(con.execute(
        "SELECT * FROM renderers WHERE removed_at IS NULL ORDER BY builtin DESC, name, id"))


def _row(con, renderer_id) -> dict | None:
    rows = _dicts(con.execute("SELECT * FROM renderers WHERE id = ?", (renderer_id,)))
    return rows[0] if rows else None


def _compute(r) -> dict:
    raw = _get(r, "compute", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _probe(r) -> dict | None:
    raw = _get(r, "gpu_probe", "")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "null")
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def ensure_builtin(con, now=None) -> None:
    """Create the built-in renderer's row if it is missing (migration 0019 also
    does). Never changes an existing row."""
    con.execute("INSERT OR IGNORE INTO renderers (id, name, builtin, enabled, created_at) "
                "VALUES (?, ?, 1, 1, ?)", (BUILTIN_ID, BUILTIN_NAME, _now_dt(now).strftime(TS_FORMAT)))


# ── videos ────────────────────────────────────────────────────────────────────

def video_kind(video) -> str:
    """'cartoon_3d', 'mascot' or 'dom'. Cartoon 3D wins over a mascot (the pair
    is refused before render anyway). A video dict may carry `scene_cartoon`
    truthy when its written scene-config is a Cartoon 3D world — the gateway
    sets it at claim time, as the renderer's scene-config check did before."""
    if (_get(video, "scene_cartoon")
            or _get(video, "visual_style", "") == "cartoon_3d"
            or _get(video, "resolved_renderer", "") == "cartoon_3d"):
        return "cartoon_3d"
    if _get(video, "mascot_id", ""):
        return "mascot"
    return "dom"


def requires_gpu(video) -> bool:
    """Cartoon 3D and mascots render on the GPU only (policy: on the CPU they
    take hours). Every other video renders anywhere."""
    return video_kind(video) != "dom"


# ── renderer state ────────────────────────────────────────────────────────────

def is_online(r, now) -> bool:
    age = age_secs(_get(r, "last_heartbeat_at", ""), now)
    return age is not None and age <= ONLINE_SECS


def gpu_capable(r) -> bool:
    """Not removed, enabled, and its last GPU probe passed — online or not, any
    version. "Some GPU-capable renderer exists" is what keeps a GPU video
    waiting rather than failing it at once."""
    return (not _get(r, "removed_at")) and bool(_get(r, "enabled", 0)) and bool(_get(r, "gpu_verified", 0))


def gpu_capable_exists(con) -> bool:
    return con.execute("SELECT 1 FROM renderers WHERE removed_at IS NULL AND enabled = 1 "
                       "AND gpu_verified = 1 LIMIT 1").fetchone() is not None


def needs_upgrade(r, main_version: str) -> bool:
    """A renderer that reported a version other than main's. One that has never
    reported a version is not "needs upgrade" (it has never connected); it is
    still never handed work, because the scheduler requires an exact match."""
    version = _get(r, "version", "")
    return bool(version) and version != main_version


def _main_version(main_version):
    if main_version is not None:
        return main_version
    from tubematic_core.version import version
    return version()


def gpu_status(con) -> dict:
    """The install's GPU state across every renderer.

    "status" uses exactly the values the existing gates understand (the old
    single-renderer probe's): "working" if any renderer is GPU-capable; else
    "unknown" if any enabled renderer has not probed yet (its fix is a test,
    not an install, and that message must not flip to "needs a GPU" before the
    first probe); else "not_usable" if an enabled renderer has a GPU configured
    whose probe failed; else "not_configured".

    "renderers" summarises each renderer not removed: id, name, builtin,
    enabled, gpu_verified, configured, ok, gpu (the configured GPU's name or
    None), error and probe (the parsed last probe, or None).
    """
    summary, statuses = [], set()
    for r in _renderer_rows(con):
        probe = _probe(r)
        enabled = bool(r["enabled"])
        gpu = (probe or {}).get("gpu")
        summary.append({
            "id": r["id"], "name": r["name"], "builtin": bool(r["builtin"]), "enabled": enabled,
            "gpu_verified": bool(r["gpu_verified"]),
            "configured": bool(probe and probe.get("configured")),
            "ok": bool(probe and probe.get("ok") is True),
            "gpu": gpu.get("name") if isinstance(gpu, dict) else None,
            "error": str((probe or {}).get("error") or ""),
            "probe": probe,
        })
        if gpu_capable(r):
            statuses.add("working")
        elif enabled and probe is None:
            statuses.add("unknown")
        elif enabled and probe.get("configured") and not probe.get("ok"):
            statuses.add("not_usable")
    for status in ("working", "unknown", "not_usable"):
        if status in statuses:
            return {"status": status, "renderers": summary}
    return {"status": "not_configured", "renderers": summary}


def renderer_states(con, now, main_version=None) -> list[dict]:
    """One dict per renderer not removed (the built-in first): id, name,
    builtin, enabled, online, state, needs_upgrade, gpu_verified,
    last_heartbeat_at, current_video_id, last_error, credential_expires_at,
    plus gpu_configured / gpu_error from its last probe and version."""
    main = _main_version(main_version)
    out = []
    for r in _renderer_rows(con):
        probe = _probe(r)
        out.append({
            "id": r["id"], "name": r["name"], "builtin": bool(r["builtin"]),
            "enabled": bool(r["enabled"]), "online": is_online(r, now), "state": r["state"],
            "needs_upgrade": needs_upgrade(r, main), "version": r["version"],
            "gpu_verified": bool(r["gpu_verified"]), "gpu_probed": probe is not None,
            "gpu_configured": bool(probe and probe.get("configured")),
            "gpu_error": str((probe or {}).get("error") or ""),
            "last_heartbeat_at": r["last_heartbeat_at"], "current_video_id": r["current_video_id"],
            "last_error": r["last_error"], "credential_expires_at": r["credential_expires_at"],
        })
    return out


def describe_state(s: dict, main_version: str) -> str:
    """"<name>: <state>" for one renderer_states() entry, e.g.
    "Studio PC: offline since 2026-11-08T10:00:00Z, GPU working"."""
    parts = []
    if not s["enabled"]:
        parts.append("disabled")
    elif not s["last_heartbeat_at"]:
        parts.append("never connected")
    elif not s["online"]:
        parts.append(f"offline since {s['last_heartbeat_at']}")
    elif s["needs_upgrade"]:
        parts.append(f"needs upgrade (runs {s['version']}, main runs {main_version})")
    if s["gpu_verified"]:
        parts.append("GPU working")
    elif not s["gpu_probed"]:
        parts.append("GPU not tested yet")
    elif s["gpu_configured"]:
        parts.append("GPU test failed: " + (s["gpu_error"] or "no reason given"))
    else:
        parts.append("no GPU configured")
    return f"{s['name']}: {', '.join(parts)}"


def gpu_unavailable_reason(con, now=None, main_version=None) -> str:
    """Why no renderer can take a GPU render right now, naming every renderer
    not removed and its state. Used in FAILED comments and refusals, where the
    human needs to know which machine to fix, not just "no GPU"."""
    main = _main_version(main_version)
    states = renderer_states(con, now if now is not None else now_ts(), main)
    if not states:
        return "No renderer can render on a GPU: no renderer is set up."
    return ("No renderer can render on a GPU right now. "
            + "; ".join(describe_state(s, main) for s in states) + ".")


# ── scheduling (pure) ─────────────────────────────────────────────────────────

def _frames(value) -> int:
    try:
        frames = int(value)
    except (TypeError, ValueError):
        return DEFAULT_FRAMES
    return frames if frames > 0 else DEFAULT_FRAMES


def estimate_secs(timings_for_kind, frames, renderer) -> float:
    """How long `renderer` should take for `frames` frames of one kind.

    The median seconds-per-frame of its last TIMINGS_WINDOW timings of that
    kind (`timings_for_kind`: dicts with "frames" and "seconds", oldest first —
    or carrying "id", which orders them). A median, so one stalled-then-retried
    render does not make a machine look slow for the next five jobs. With no
    timings, a prior: GPU_PRIOR on a verified GPU, else CPU_PRIOR scaled by its
    core count."""
    rows = [t for t in (timings_for_kind or []) if (_get(t, "frames", 0) or 0) > 0]
    if rows and all(_get(t, "id") is not None for t in rows):
        rows = sorted(rows, key=lambda t: _get(t, "id"))
    rows = rows[-TIMINGS_WINDOW:]
    if rows:
        per_frame = statistics.median(float(_get(t, "seconds", 0) or 0) / float(_get(t, "frames"))
                                      for t in rows)
    elif _get(renderer, "gpu_verified", 0):
        per_frame = GPU_PRIOR_SECS_PER_FRAME
    else:
        try:
            cpus = int(_compute(renderer).get("cpus") or 0)
        except (TypeError, ValueError):
            cpus = 0
        per_frame = CPU_PRIOR_SECS_PER_FRAME * (CPU_PRIOR_REFERENCE_CPUS / max(1, cpus))
    return per_frame * max(0, int(frames or 0))


def _timings_by(timings) -> dict:
    grouped = {}
    for t in timings or []:
        grouped.setdefault((_get(t, "renderer_id", ""), _get(t, "kind", "")), []).append(t)
    return grouped


def time_until_free(renderer, timings, now) -> float:
    """0 for an idle renderer. For a busy one (a "current" dict: kind, frames,
    started_at) its estimate for the current job minus the time already spent,
    never below 0."""
    current = _get(renderer, "current")
    if not current:
        return 0.0
    kind = _get(current, "kind", "dom")
    est = estimate_secs(_timings_by(timings).get((_get(renderer, "id"), kind), []),
                        _frames(_get(current, "frames")), renderer)
    elapsed = age_secs(_get(current, "started_at", ""), now) or 0.0
    return max(0.0, est - elapsed)


def pick_video(queue, renderers, timings, me, now, main_version) -> str | None:
    """The video renderer `me` should take now, or None.

    queue: RENDER_QUEUED videos as dicts (id, updated_at, visual_style,
      resolved_renderer, mascot_id, optional scene_cartoon, frames).
    renderers: renderer dicts (rows of `renderers`), each optionally carrying
      "current": {"kind", "frames", "started_at"} while it renders.
    timings: render_timings rows (renderer_id, kind, frames, seconds, id).
    me: the calling renderer's id. It is treated as online and free — it is
      calling, and it only claims when idle.

    In queue order (updated_at, id), skipping any video the caller may not take
    (a GPU video on a renderer without a verified GPU). A candidate goes to the
    caller when its estimated finish is within FINISH_TOLERANCE of the best
    finish across every eligible online renderer (time until free + estimate),
    or when the video has waited longer than STARVATION_SECS — so a slow
    machine never takes a job a much faster one would finish sooner, yet no
    video waits forever for the fast machine. Otherwise the next video is
    considered. A disabled, removed or version-mismatched caller gets nothing.
    """
    by_id = {_get(r, "id"): r for r in renderers}
    caller = by_id.get(me)
    if caller is None or _get(caller, "removed_at") or not _get(caller, "enabled", 0):
        return None
    if _get(caller, "version", "") != main_version:
        return None
    grouped = _timings_by(timings)

    def eligible(r, gpu: bool) -> bool:
        if _get(r, "removed_at") or not _get(r, "enabled", 0):
            return False
        if _get(r, "version", "") != main_version:
            return False
        if _get(r, "id") != me and not is_online(r, now):
            return False
        return bool(_get(r, "gpu_verified", 0)) or not gpu

    ordered = sorted(queue, key=lambda v: (_get(v, "updated_at", ""), _get(v, "id", "")))
    for video in ordered:
        gpu = requires_gpu(video)
        if not eligible(caller, gpu):
            continue
        kind, frames = video_kind(video), _frames(_get(video, "frames"))
        mine = estimate_secs(grouped.get((me, kind), []), frames, caller)
        best = mine
        for r in renderers:
            rid = _get(r, "id")
            if rid == me or not eligible(r, gpu):
                continue
            finish = time_until_free(r, timings, now) + estimate_secs(grouped.get((rid, kind), []), frames, r)
            best = min(best, finish)
        waited = age_secs(_get(video, "updated_at", ""), now) or 0.0
        if mine <= best * FINISH_TOLERANCE or waited > STARVATION_SECS:
            return _get(video, "id")
    return None


def recent_timings(con, window: int = TIMINGS_WINDOW) -> list[dict]:
    """The last `window` render_timings rows per (renderer, kind), oldest first
    within each — exactly what pick_video and estimate_secs read."""
    return _dicts(con.execute(
        "SELECT id, renderer_id, kind, on_gpu, frames, seconds, created_at FROM ("
        " SELECT *, ROW_NUMBER() OVER (PARTITION BY renderer_id, kind ORDER BY id DESC) AS rn"
        " FROM render_timings) WHERE rn <= ? ORDER BY renderer_id, kind, id", (window,)))


# ── credentials ───────────────────────────────────────────────────────────────

def authenticate(con, token, now, builtin_token=None) -> dict | None:
    """The renderer row `token` authenticates, or None.

    The built-in renderer's token is the builtin_renderer_token secret, which
    the caller reads fresh per request and passes as `builtin_token`; compared
    in constant time, it never expires and needs no row update when rotated.

    A remote renderer's token matches the hash of its current credential or of
    the previous one (kept from a rotation until the new one is first used, so
    a renderer that never received the rotated credential is not locked out).
    The first use of the current credential clears the previous. An expired
    credential writes last_error and raises CredentialExpired. A removed
    renderer never authenticates. A disabled one does (the gateway answers it
    "disabled", which is how it learns to stop).
    """
    if not isinstance(token, str) or not token:
        return None
    if builtin_token and hmac.compare_digest(token.encode("utf-8"), builtin_token.encode("utf-8")):
        row = _row(con, BUILTIN_ID)
        return row if row and not row["removed_at"] else None
    digest = hash_secret(token)
    rows = _dicts(con.execute(
        "SELECT * FROM renderers WHERE removed_at IS NULL AND builtin = 0 "
        "AND (credential_hash = ? OR (previous_credential_hash != '' AND previous_credential_hash = ?))",
        (digest, digest)))
    if not rows:
        return None
    row = rows[0]
    expires = parse_ts(row["credential_expires_at"])
    if expires is not None and _now_dt(now) >= expires:
        con.execute("UPDATE renderers SET last_error = ? WHERE id = ?", (CREDENTIAL_EXPIRED_ERROR, row["id"]))
        raise CredentialExpired(row["id"])
    if row["credential_hash"] == digest and row["previous_credential_hash"]:
        con.execute("UPDATE renderers SET previous_credential_hash = '' WHERE id = ?", (row["id"],))
        row["previous_credential_hash"] = ""
    return row


def maybe_rotate(con, renderer_id, now) -> tuple[str | None, str]:
    """A new credential for a remote renderer whose current one is at least
    ROTATE_AFTER_DAYS old, else (None, current expiry). Called from the
    heartbeat, after authenticate().

    The current hash moves to previous_credential_hash, so the renderer's
    credential keeps working until it first uses the new one. While a rotation
    is pending (previous still set) the renderer has not used the new
    credential, i.e. it never received it; so a new one is issued again on
    each heartbeat, replacing only the undelivered one and never the previous,
    which is the one the renderer holds. The built-in renderer never rotates
    here (its token is a secret file, rotated by --rotate-tokens)."""
    row = _row(con, renderer_id)
    if row is None or row["builtin"] or row["removed_at"]:
        return None, ""
    issued_age = age_secs(row["credential_issued_at"], now)
    pending = bool(row["previous_credential_hash"])
    due = issued_age is None or issued_age >= ROTATE_AFTER_DAYS * 86400
    if not (pending or due):
        return None, row["credential_expires_at"]
    credential = new_secret()
    issued = _now_dt(now).strftime(TS_FORMAT)
    expires = ts_add(now, CREDENTIAL_DAYS * 86400)
    previous = row["previous_credential_hash"] if pending else row["credential_hash"]
    con.execute("UPDATE renderers SET credential_hash = ?, previous_credential_hash = ?, "
                "credential_issued_at = ?, credential_expires_at = ? WHERE id = ?",
                (hash_secret(credential), previous, issued, expires, renderer_id))
    return credential, expires


def enroll(con, secret, machine_id, name, host, version, compute, now) -> dict:
    """Redeem a one-time enrollment secret. Returns {"renderer_id",
    "credential", "credential_expires_at"}; raises EnrollmentInvalid for an
    unknown, used or expired secret.

    The secret is consumed by a guarded UPDATE, so two concurrent redemptions
    of one secret cannot both succeed. Re-enrolling a machine that already has
    a (not removed) renderer — same machine_id, a random id the renderer keeps
    in its state directory — replaces that row's credential, version, compute
    and host instead of adding a second row, so reinstalling a host does not
    leave a ghost renderer behind. The name the enrollment was issued with
    wins; otherwise the renderer's own, then its host name."""
    if not isinstance(secret, str) or not secret:
        raise EnrollmentInvalid("enrollment_invalid")
    stamp = _now_dt(now).strftime(TS_FORMAT)
    digest = hash_secret(secret)
    cur = con.execute("UPDATE renderer_enrollments SET used_at = ? "
                      "WHERE secret_hash = ? AND used_at IS NULL AND expires_at > ?", (stamp, digest, stamp))
    if cur.rowcount != 1:
        raise EnrollmentInvalid("enrollment_invalid")
    issued_name = con.execute("SELECT name FROM renderer_enrollments WHERE secret_hash = ?",
                              (digest,)).fetchone()[0] or ""
    compute_json = json.dumps(compute if isinstance(compute, dict) else {})
    credential = new_secret()
    expires = ts_add(now, CREDENTIAL_DAYS * 86400)
    machine_id = machine_id if isinstance(machine_id, str) else ""
    host = host if isinstance(host, str) else ""
    existing = None
    if machine_id:
        existing = con.execute("SELECT id FROM renderers WHERE machine_id = ? AND builtin = 0 "
                               "AND removed_at IS NULL ORDER BY created_at LIMIT 1", (machine_id,)).fetchone()
    if existing:
        renderer_id = existing[0]
        con.execute("UPDATE renderers SET credential_hash = ?, previous_credential_hash = '', "
                    "credential_issued_at = ?, credential_expires_at = ?, version = ?, compute = ?, "
                    "host = ?, last_error = '', name = CASE WHEN ? != '' THEN ? ELSE name END WHERE id = ?",
                    (hash_secret(credential), stamp, expires, version or "", compute_json, host,
                     issued_name, issued_name, renderer_id))
    else:
        renderer_id = "r_" + secrets.token_hex(6)
        display = issued_name or (name if isinstance(name, str) else "") or host or "Renderer"
        con.execute("INSERT INTO renderers (id, name, builtin, enabled, machine_id, host, credential_hash, "
                    "credential_issued_at, credential_expires_at, version, compute, created_at) "
                    "VALUES (?, ?, 0, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (renderer_id, display[:100], machine_id, host, hash_secret(credential), stamp,
                     expires, version or "", compute_json, stamp))
    con.execute("UPDATE renderer_enrollments SET renderer_id = ? WHERE secret_hash = ?", (renderer_id, digest))
    return {"renderer_id": renderer_id, "credential": credential, "credential_expires_at": expires}
