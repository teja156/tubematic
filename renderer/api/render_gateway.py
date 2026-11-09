"""The render gateway: the only thing a renderer talks to.

A second Flask app, served by server.py in its own thread on :4443 over TLS
(self-signed; renderers pin the certificate). The pipeline API on :4000 is
untouched. Every renderer — the built-in one beside the API and any remote
host — calls the same routes:

  GET  /v1/version                    open: main's version
  POST /v1/enroll                     open: redeem a one-time enrollment secret
  POST /v1/heartbeat                  state, GPU probe, lease extension, stop list, rotation
  POST /v1/claim                      the next video for this renderer, or 204
  GET  /v1/jobs/<id>/bundle           the job's files as one uncompressed tar stream
  PUT  /v1/jobs/<id>/output           the rendered mp4, streamed
  POST /v1/jobs/<id>/result           how the render ended

Everything but version and enroll needs `Authorization: Bearer <credential>`,
resolved by tubematic_core.renderers.authenticate: the built-in renderer's
token is the builtin_renderer_token secret, read per request so a rotation
applies with no restart; a remote renderer's is its enrolled credential. The
API's own api_token is NOT a renderer credential and is refused here, so the
dashboard's token cannot claim or rewrite renders.

The gateway decides; the renderer only renders. Which video a renderer gets
(tubematic_core.renderers.pick_video), the refusals made before any render
(an unusable id, missing job files, a Cartoon 3D video holding a mascot, a
mascot whose code cannot be staged), and what a failed render does to its
video (render_results) all happen here, against the database. A claim holds
its video by a lease that every heartbeat extends, and is named by a claim id
that is new on every claim (videos.render_claim_id). The bundle, the upload
and the result must carry it (the X-Render-Claim header) and are refused (403)
to anyone but the holder of that very claim, so a renderer that lost its
lease — even one that has since claimed the same video again — cannot
overwrite the work of the claim that took over: an upload is checked against
the claim once more just before it is renamed into place (409 claim_lost),
and a failure result moves the video only while its claim still holds. The
heartbeat is fenced the same way: it reports the claim it renders, extends
only that claim's lease, and its stop list names claims, so a heartbeat for an
earlier claim of a video can neither extend nor stop a newer one.

What an untrusted renderer can make the gateway hold is bounded: the JSON
routes read at most MAX_JSON_BYTES (413 past it, before any parse — the open
enroll route included); an upload is at most MAX_OUTPUT_BYTES, one at a time
per claim (409 upload_in_progress), MAX_CONCURRENT_UPLOADS at once in all
(503 busy), and never below MIN_FREE_BYTES of free space on the output
filesystem (507 insufficient_storage).

And for how long, since a byte limit alone lets a client hold a thread by
sending slowly (see _GatewayRequestHandler): every read and write on a
connection must make progress within GATEWAY_IDLE_TIMEOUT_SECS; the TLS
handshake, request line and headers must all arrive within REQUEST_HEAD_SECS;
a JSON body within JSON_BODY_SECS (408 body_timeout). A protected route is
authenticated from its headers before a byte of its body is read, so only
the open enroll route reads a body for a caller nobody knows, and at most
MAX_ENROLL_READERS do at once (503 busy); one renderer has at most
MAX_REQUESTS_PER_RENDERER requests in the gateway, each counted until its
reply is sent and drained; and the process holds at most MAX_CONNECTIONS
connections, refused before a thread is made for one past it. An upload has no total deadline,
only the idle one: a slow home link is a legitimate reason for a long
upload, and the per-claim and global upload caps bound how many there are.

Uploads are written into UPLOAD_TMP_DIR under the output directory and
renamed into place, so a temp file a crash left behind is never beside a
video: the directory's leftovers are cleared when the gateway starts.

A renderer renders one video at a time, and the claim enforces it: a renderer
that already holds an unfinished claim is answered that claim again (the same
reply, the same claim id — what a renderer whose claim reply was lost needs),
never a second video.
"""
import json
import logging
import os
import shutil
import ssl
import stat
import tarfile
import threading
import time
import uuid
from pathlib import Path

from flask import Flask, Response, g, jsonify, request
from werkzeug.exceptions import ClientDisconnected

import db
import pipeline
import render_results
from tubematic_core import jobfiles as tjobs
from tubematic_core import mascots as tmascots
from tubematic_core import renderers
from tubematic_core.auth import (TLS_CERT_NAME, TLS_KEY_NAME, SecretMissing, read_secret,
                                 secrets_dir as default_secrets_dir)
from tubematic_core.version import version as current_version

log = logging.getLogger("render_gateway")

GATEWAY_API_VERSION = 1
BUILTIN_TOKEN_NAME = "builtin_renderer_token"
OPEN_ENDPOINTS = {"gateway_version", "gateway_enroll"}
OUTCOMES = ("success", "failed", "stalled", "timeout", "error")
# A refused video drops out of the queue, so a claim tries the next one; the
# cap only bounds a queue that keeps changing under it.
MAX_CLAIM_ATTEMPTS = 50
CHUNK_BYTES = 1 << 20
CLAIM_HEADER = "X-Render-Claim"


def _env_int(name: str, default: int) -> int:
    """A positive integer from the environment, else `default`."""
    try:
        value = int(os.getenv(name, ""))
    except ValueError:
        return default
    return value if value > 0 else default


# A renderer's body is untrusted, so every byte it can make the gateway hold
# is bounded. The output volume holds the database too: a full disk there
# stops the whole install, not only renders.
#
# The largest mp4 one upload may be: TUBEMATIC_MAX_OUTPUT_BYTES, default
# 8 GiB (a 3-minute Short is a few hundred MB).
MAX_OUTPUT_BYTES = _env_int("TUBEMATIC_MAX_OUTPUT_BYTES", 8 << 30)
# Uploads streaming at once, across every claim: TUBEMATIC_MAX_CONCURRENT_UPLOADS
# (default 4). One claim never has two (its renderer's retry of an upload
# still streaming is refused), so this bounds the temp files in flight.
MAX_CONCURRENT_UPLOADS = _env_int("TUBEMATIC_MAX_CONCURRENT_UPLOADS", 4)
# The free space an upload must leave on the output filesystem:
# TUBEMATIC_MIN_FREE_BYTES, default 2 GiB. Checked against the declared size
# before anything is written, and again every DISK_CHECK_BYTES while it
# streams (a chunked body declares nothing, and other writers share the disk).
MIN_FREE_BYTES = _env_int("TUBEMATIC_MIN_FREE_BYTES", 2 << 30)
DISK_CHECK_BYTES = 64 << 20
# The Retry-After of every 503 busy (uploads, enrollment, a renderer's
# requests at once).
BUSY_RETRY_AFTER_SECS = 10
# Every other route takes a small JSON body (enroll, heartbeat, claim,
# result): at most MAX_JSON_BYTES, counted as it is read, before any parse.
# The enroll route is open, so this is what an unauthenticated caller can
# make the gateway hold.
MAX_JSON_BYTES = 64 << 10
JSON_ENDPOINTS = {"gateway_enroll", "heartbeat_route", "claim_route", "result_route"}

# Time bounds (the werkzeug server gives a thread to every connection and,
# by itself, waits forever on a client that stops sending):
# - every read and write on a connection must make progress within
#   GATEWAY_IDLE_TIMEOUT_SECS (the socket timeout);
# - the TLS handshake, the request line and the headers must all arrive
#   within REQUEST_HEAD_SECS of the connection, so a client trickling header
#   bytes cannot hold a thread either;
# - a JSON body must arrive within JSON_BODY_SECS (408 body_timeout); it is
#   at most 64 KiB, which any working link sends in far less;
# - an upload has no total deadline, only the idle one. A long video over a
#   slow home link takes as long as it takes, and a renderer that gave up on
#   an upload is refused a second one for the same claim while it streams;
# - once the reply is out, werkzeug reads what is left of an unread body so
#   the client sees the reply rather than a reset. That courtesy gets
#   DRAIN_SECS, then the connection is closed.
GATEWAY_IDLE_TIMEOUT_SECS = 60
REQUEST_HEAD_SECS = 30
JSON_BODY_SECS = 30
DRAIN_SECS = 5
# Unauthenticated bodies being read at once (the enroll route): past it, 503
# busy before a byte is read.
MAX_ENROLL_READERS = 4
# Requests one renderer may have in the gateway at once, each counted from
# its authentication until its reply has been sent and what was left of its
# body drained (a streamed bundle until its last byte). A renderer makes at
# most three (its heartbeat, and one job request from its loop, or a retry
# overlapping one the gateway is still finishing); past it, 503 busy.
MAX_REQUESTS_PER_RENDERER = 8
# Connections the gateway holds at once, across every client, each counted
# from its accept to its close: past it a connection is closed at once,
# before a thread is made for it. werkzeug's threaded server makes a thread
# for every connection before its TLS handshake, before any cap above can
# see it, so without this a client opening connections faster than
# REQUEST_HEAD_SECS ends them could grow threads without limit in the API's
# process (the dashboard's API included). werkzeug closes every connection
# after one request, so a connection is one request or one still arriving.
# 128 leaves room for 15 renderers each at MAX_REQUESTS_PER_RENDERER plus
# MAX_ENROLL_READERS (a renderer really makes at most three at once), while
# its threads cost little. A client holding every slot only delays
# renderers (each held slot ends by REQUEST_HEAD_SECS, and a renderer retries
# a refused connection); it cannot take the API down.
MAX_CONNECTIONS = 128
# Where uploads are written before they are renamed into place: a directory
# of the gateway's own on the output filesystem (os.replace stays a rename).
# Its leftovers (a crash mid-upload) are cleared when the gateway starts, and
# any older than UPLOAD_ORPHAN_SECS that no upload of this process is writing
# are swept whenever an upload is admitted. Only names ending UPLOAD_SUFFIX
# are ever removed, and nothing in it is followed.
UPLOAD_TMP_DIR = ".gateway-uploads"
UPLOAD_SUFFIX = ".upload"
UPLOAD_ORPHAN_SECS = 6 * 3600
# The connection's bounded reader, in the WSGI environ, so a route can set
# its body's deadline (absent under a test client).
READER_KEY = "tubematic.gateway_reader"
# Where a request's release of its per-renderer count waits, in the WSGI
# environ, when the app is served by make_gateway_server: called once the
# response is closed (after werkzeug's drain), or when the connection ends
# without that close (absent under Flask's test client, which releases at
# teardown).
RELEASE_KEY = "tubematic.gateway_release"
_TAR_BLOCK = tarfile.BLOCKSIZE          # 512
_TAR_RECORD = tarfile.RECORDSIZE        # 10240

# Members of a bundle, relative to the job, and where the cartoon extras live.
MASCOT_MEMBER = "mascot.js"
CARTOON_SOURCE = ("cartoon", "source.json")
CARTOON_MIX = ("cartoon", "audio", "mix", "mix.wav")
FLAT_SCENES = "_flat"


class BundleUnavailable(Exception):
    """The job's files cannot be bundled any more (deleted or tampered with
    since the claim). The renderer reports the render as an error."""


def _remotion_dir() -> Path:
    # The API runs in the same image as the renderer: /app/remotion holds the
    # builtin mascots' files and, mounted, the shared generated scene tree.
    return Path(os.getenv("TUBEMATIC_REMOTION_DIR", "/app/remotion"))


class _BodyTooLarge(Exception):
    pass


class _BodyUnread(Exception):
    """The request body could not be read: it stopped arriving in time
    (`timed_out`), or the client went away."""

    def __init__(self, timed_out: bool):
        super().__init__("timed out" if timed_out else "incomplete")
        self.timed_out = timed_out


def _read_chunk(stream, n: int) -> bytes:
    """One read of the request body. A read that timed out (the socket's idle
    timeout, or the body's deadline) or found the client gone raises
    _BodyUnread: werkzeug reports both as ClientDisconnected for a body with
    a Content-Length and as the OSError itself for a chunked one."""
    try:
        return stream.read(n)
    except (ClientDisconnected, OSError) as e:
        raise _BodyUnread(isinstance(e, TimeoutError) or isinstance(e.__context__, TimeoutError)) from None


def _body_unread(e: _BodyUnread, what: str):
    if e.timed_out:
        log.warning(f"gateway: {request.method} {request.path} ended: {what} stopped arriving in time")
        return _err(408, "body_timeout")
    log.warning(f"gateway: {request.method} {request.path} ended: the client left before sending {what}")
    return _err(400, "body_incomplete")


def _read_json_body() -> dict:
    """The request's JSON object, read with a counted limit: a declared
    Content-Length over MAX_JSON_BYTES is refused before a byte is read, and
    a chunked (or lying) body is read only until it passes the limit. Never
    request.get_json(), which reads whatever arrives. Anything but a JSON
    object is {}. The whole body must arrive within JSON_BODY_SECS, or
    _BodyUnread(timed_out=True): checked between reads, and (on the real
    server) by the connection's reader, so a read blocked on a trickle ends
    at the deadline too."""
    length = request.content_length
    if length is not None and length > MAX_JSON_BYTES:
        raise _BodyTooLarge()
    deadline = time.monotonic() + JSON_BODY_SECS
    reader = request.environ.get(READER_KEY)
    if reader is not None:
        reader.deadline = deadline
    try:
        stream = request.stream
        buf = bytearray()
        while True:
            if time.monotonic() >= deadline:
                raise _BodyUnread(timed_out=True)
            chunk = _read_chunk(stream, min(64 << 10, MAX_JSON_BYTES + 1 - len(buf)))
            if not chunk:
                break
            buf += chunk
            if len(buf) > MAX_JSON_BYTES:
                raise _BodyTooLarge()
    finally:
        if reader is not None:
            reader.deadline = None
    if not buf:
        return {}
    try:
        data = json.loads(bytes(buf))
    except (ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def _body() -> dict:
    return getattr(g, "json_body", None) or {}


def _str(value, cap: int = 2000) -> str:
    return value[:cap] if isinstance(value, str) else ""


def _err(code: int, error: str, **extra):
    return jsonify({"error": error, **extra}), code


def _busy():
    resp, code = _err(503, "busy")
    resp.headers["Retry-After"] = str(BUSY_RETRY_AFTER_SECS)
    return resp, code


def _who() -> str:
    r = getattr(g, "renderer", None)
    return f"renderer {r['id']}" if r else "an unauthenticated caller"


def _frames_of(jobs_dir, video_id) -> int | None:
    """timeline.json's totalFrames, or None when it cannot be read."""
    try:
        timeline = tjobs.job_file(jobs_dir, video_id, tjobs.TIMELINE)
        frames = int(json.loads(timeline.read_text(encoding="utf-8")).get("totalFrames", 0))
    except (tjobs.UnsafePath, OSError, ValueError, TypeError, AttributeError):
        return None
    return frames if frames > 0 else None


def _scene_cartoon(jobs_dir, video_id) -> bool:
    try:
        return render_results.scene_config_is_cartoon3d(
            tjobs.job_file(jobs_dir, video_id, tjobs.SCENE_CONFIG))
    except tjobs.UnsafePath:
        return False


def _video_facts(jobs_dir, row) -> dict:
    """A video row as the scheduler and the claim see it: the row plus
    scene_cartoon (its written scene-config is a Cartoon 3D world, which makes
    an `auto` video GPU-only too) and frames."""
    v = dict(row)
    v["scene_cartoon"] = _scene_cartoon(jobs_dir, v["id"])
    v["frames"] = _frames_of(jobs_dir, v["id"])
    return v


# ── tar streaming ─────────────────────────────────────────────────────────────

def _tar_header(name: str, size: int, mtime: float) -> bytes:
    info = tarfile.TarInfo(name)
    info.size = size
    info.mtime = int(mtime)
    info.mode = 0o644
    info.type = tarfile.REGTYPE
    return info.tobuf(tarfile.PAX_FORMAT, "utf-8", "surrogateescape")


def _stream_tar(members):
    """Yield an uncompressed tar of `members` — (arcname, Path or bytes) —
    chunk by chunk. Each file is opened (without following a symlink) only
    when its turn comes, and read CHUNK_BYTES at a time, so memory never holds
    more than one chunk of one file. A file that shrank while being sent is
    padded to the size its header promised, so the archive stays readable; one
    that vanished or turned into a symlink is skipped."""
    total = 0
    for name, source in members:
        if isinstance(source, bytes):
            header = _tar_header(name, len(source), 0)
            pad = -len(source) % _TAR_BLOCK
            total += len(header) + len(source) + pad
            yield header + source + b"\0" * pad
            continue
        try:
            fd = os.open(source, os.O_RDONLY | os.O_NOFOLLOW)
        except OSError:
            log.warning(f"bundle: {name} is gone or is not a plain file; skipped")
            continue
        with os.fdopen(fd, "rb") as fh:
            st = os.fstat(fh.fileno())
            if not stat.S_ISREG(st.st_mode):
                continue
            size = st.st_size
            header = _tar_header(name, size, st.st_mtime)
            total += len(header)
            yield header
            left = size
            while left > 0:
                chunk = fh.read(min(CHUNK_BYTES, left))
                if not chunk:
                    chunk = b"\0" * min(CHUNK_BYTES, left)
                left -= len(chunk)
                total += len(chunk)
                yield chunk
            pad = -size % _TAR_BLOCK
            total += pad
            if pad:
                yield b"\0" * pad
    end = b"\0" * (2 * _TAR_BLOCK)
    total += len(end)
    yield end + b"\0" * (-total % _TAR_RECORD)


def _plain_files(root: Path, prefix: str) -> list:
    """Every regular file under `root` as (prefix/relpath, path), sorted;
    symlinks — to files or directories — are skipped, never followed."""
    out = []
    if not root.is_dir() or root.is_symlink():
        return out
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(d for d in dirnames if not os.path.islink(os.path.join(dirpath, d)))
        for f in sorted(filenames):
            path = os.path.join(dirpath, f)
            try:
                if not stat.S_ISREG(os.lstat(path).st_mode):
                    continue
            except OSError:
                continue
            rel = os.path.relpath(path, root).replace(os.sep, "/")
            out.append((f"{prefix}/{rel}", Path(path)))
    return out


def _flat_scene_names(scene_config: Path) -> list:
    """The legacy flat generated scenes a scene-config names: type generated,
    not from the installed library, and a src with no "/" in it."""
    try:
        config = json.loads(scene_config.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    scenes = config.get("scenes") if isinstance(config, dict) else None
    names = []
    for s in scenes if isinstance(scenes, list) else []:
        if not isinstance(s, dict) or s.get("type") != "generated":
            continue
        src = s.get("src")
        if s.get("source", "generated") == "installed" or not isinstance(src, str) or not src or "/" in src:
            continue
        if src not in names:
            names.append(src)
    return names


def _is_plain_file(path: Path) -> bool:
    return path.is_file() and not path.is_symlink()


def _upload_dir(output_dir) -> Path:
    """The gateway's upload temp directory under `output_dir`, created when
    missing. UnsafePath when something has put a symlink under its name."""
    d = tjobs.join_below(output_dir, UPLOAD_TMP_DIR)
    d.mkdir(parents=True, exist_ok=True)
    return d


def _sweep_uploads(output_dir, live=frozenset(), older_than=None) -> int:
    """Remove leftover temp uploads from the upload directory: entries named
    *UPLOAD_SUFFIX that are not `live` (being written by this process) and,
    when `older_than` is given, were last written more than that many
    seconds ago. A symlink is removed, never followed; a directory is left
    alone. Returns how many were removed. Never raises."""
    try:
        d = _upload_dir(output_dir)
        entries = list(os.scandir(d))
    except (tjobs.UnsafePath, OSError) as e:
        log.warning(f"gateway: the upload directory cannot be swept: {e}")
        return 0
    now = time.time()
    removed = 0
    for entry in entries:
        if not entry.name.endswith(UPLOAD_SUFFIX) or entry.name in live:
            continue
        try:
            st = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(st.st_mode):
                continue
            if older_than is not None and now - st.st_mtime < older_than:
                continue
            os.unlink(entry.path)
            removed += 1
        except OSError:
            continue
    if removed:
        log.info(f"gateway: removed {removed} abandoned upload temp file(s) from {d}")
    return removed


# ── the app ───────────────────────────────────────────────────────────────────

def create_gateway_app(db_path, jobs_dir, output_dir, secrets_dir=None, remotion_dir=None) -> Flask:
    """The gateway app. `db_path` must be the database render_results.DB_PATH
    names: in a container both come from TUBEMATIC_DB (one process, one
    database). `remotion_dir` holds the builtin mascots and the shared
    generated scene tree (default TUBEMATIC_REMOTION_DIR or /app/remotion)."""
    db_path = str(db_path)
    jobs_dir = Path(jobs_dir)
    output_dir = Path(output_dir)
    remotion = Path(remotion_dir) if remotion_dir is not None else _remotion_dir()
    generated = remotion / "src" / "scenes" / "generated"
    # Before any request: nothing is uploading yet, so every temp upload
    # left in the directory is a crash's leftover.
    _sweep_uploads(output_dir)
    app = Flask("render_gateway")

    def builtin_token():
        try:
            return read_secret(BUILTIN_TOKEN_NAME, secrets_dir)
        except SecretMissing:
            # Fail closed: with no secret file the built-in renderer cannot
            # authenticate, and nothing else matches an absent token.
            return None

    # Requests in the gateway now, per renderer id, and unauthenticated
    # (enroll) bodies being read: both counted under one lock, and checked
    # against the module's limits when each request arrives.
    counts_lock = threading.Lock()
    in_flight = {}
    enroll_readers = [0]
    app.extensions["render_gateway.in_flight"] = in_flight     # read by the tests

    def releaser(rid):
        """Gives back one request of renderer `rid`, however often it is
        called: the release is reached from more than one place."""
        done = [False]

        def release():
            with counts_lock:
                if done[0]:
                    return
                done[0] = True
                left = in_flight.get(rid, 1) - 1
                if left > 0:
                    in_flight[rid] = left
                else:
                    in_flight.pop(rid, None)
        return release

    @app.before_request
    def _authenticate():
        # Registered first: a protected route's caller is known from its
        # headers before a byte of its body is read, so an unknown caller
        # cannot make the gateway wait on a body at all.
        if request.endpoint in OPEN_ENDPOINTS:
            return None
        scheme, _, token = request.headers.get("Authorization", "").partition(" ")
        token = token.strip()
        if scheme.lower() != "bearer" or not token:
            log.warning(f"gateway: {request.method} {request.path} refused: no bearer credential")
            return _err(401, "unauthorized")
        expired = None
        with db.conn(db_path) as con:
            try:
                row = renderers.authenticate(con, token, renderers.now_ts(), builtin_token())
            except renderers.CredentialExpired as e:
                row, expired = None, e.renderer_id
        # the connection has committed authenticate's writes (last_error, a
        # cleared previous credential) by here
        if expired:
            log.warning(f"gateway: renderer {expired} refused: credential expired")
            return _err(401, "credential_expired")
        if row is None:
            log.warning(f"gateway: {request.method} {request.path} refused: unknown credential")
            return _err(401, "unauthorized")
        release = releaser(row["id"])
        with counts_lock:
            if in_flight.get(row["id"], 0) >= MAX_REQUESTS_PER_RENDERER:
                busy = True
            else:
                busy = False
                in_flight[row["id"]] = in_flight.get(row["id"], 0) + 1
                # Served for real, the count is held until the response is
                # closed — after a streamed bundle's last byte and the drain
                # of an unread body, both of which come after this request's
                # teardown (see _bounded_app). Under Flask's test client
                # there is no such close, so it goes at teardown.
                waiting = request.environ.get(RELEASE_KEY)
                if waiting is not None:
                    waiting.append(release)
                else:
                    g.release = release
        if busy:
            log.warning(f"gateway: {request.method} {request.path} from renderer {row['id']} refused: "
                        f"it already has {MAX_REQUESTS_PER_RENDERER} requests in the gateway")
            return _busy()
        g.renderer = row
        return None

    @app.teardown_request
    def _uncount(_exc):
        release = g.pop("release", None)
        if release is not None:
            release()

    @app.before_request
    def _bound_json_body():
        # After authentication: only the open enroll route reads a body for
        # a caller nobody knows, and only MAX_ENROLL_READERS at once.
        if request.endpoint not in JSON_ENDPOINTS:
            return None
        enrolling = request.endpoint == "gateway_enroll"
        if enrolling:
            with counts_lock:
                if enroll_readers[0] >= MAX_ENROLL_READERS:
                    log.warning(f"gateway: an enrollment refused: {MAX_ENROLL_READERS} enrollment bodies "
                                "are already being read")
                    return _busy()
                enroll_readers[0] += 1
        try:
            g.json_body = _read_json_body()
        except _BodyTooLarge:
            log.warning(f"gateway: {request.method} {request.path} refused: body over the "
                        f"{MAX_JSON_BYTES}-byte limit")
            return _err(413, "body_too_large", limit=MAX_JSON_BYTES)
        except _BodyUnread as e:
            return _body_unread(e, "its body")
        finally:
            if enrolling:
                with counts_lock:
                    enroll_readers[0] -= 1
        return None

    # ── open routes ──────────────────────────────────────────────────────────

    @app.get("/v1/version", endpoint="gateway_version")
    def version_route():
        return jsonify({"version": current_version(), "gateway": GATEWAY_API_VERSION})

    @app.post("/v1/enroll", endpoint="gateway_enroll")
    def enroll_route():
        body = _body()
        try:
            with db.conn(db_path) as con:
                out = renderers.enroll(con, body.get("secret"), _str(body.get("machine_id"), 200),
                                       _str(body.get("name"), 100), _str(body.get("host"), 255),
                                       _str(body.get("version"), 64),
                                       body.get("compute") if isinstance(body.get("compute"), dict) else {},
                                       renderers.now_ts())
        except renderers.EnrollmentInvalid:
            log.warning("gateway: an enrollment was refused: unknown, used or expired secret")
            return _err(403, "enrollment_invalid")
        log.info(f"gateway: renderer {out['renderer_id']} enrolled")
        return jsonify(out)

    # ── heartbeat ────────────────────────────────────────────────────────────

    @app.post("/v1/heartbeat")
    def heartbeat_route():
        me = g.renderer["id"]
        body = _body()
        main = current_version()
        if body.get("started") is True:
            # The renderer's process just started, so whatever it held is not
            # being rendered any more: re-queue it now (a retry counted, as a
            # restart always counted) rather than wait out the lease.
            with db.conn(db_path) as con:
                held = [r["id"] for r in con.execute(
                    "SELECT id FROM videos WHERE status = 'RENDERING' AND renderer_id = ? "
                    "AND render_uploaded_at = ''", (me,))]
            for vid in held:
                render_results.requeue_interrupted(vid, render_results.RESTART_COMMENT, renderer_id=me)
            if held:
                log.info(f"gateway: renderer {me} restarted; re-queued {len(held)} interrupted render(s)")

        now = renderers.now_ts()
        state = body.get("state") if body.get("state") in ("idle", "rendering") else "idle"
        video_id = _str(body.get("video_id"), 300) if state == "rendering" else ""
        claim_id = _str(body.get("claim_id"), 64) if video_id else ""
        compute = body.get("compute") if isinstance(body.get("compute"), dict) else None
        probe = body.get("gpu_probe") if isinstance(body.get("gpu_probe"), dict) else None
        reported_version = _str(body.get("version"), 64)
        with db.conn(db_path) as con:
            con.execute(
                "UPDATE renderers SET version = ?, compute = COALESCE(?, compute), state = ?, "
                "current_video_id = ?, last_error = ?, last_heartbeat_at = ? WHERE id = ?",
                (reported_version, json.dumps(compute) if compute is not None else None, state,
                 video_id, _str(body.get("last_error")), now, me))
            if probe is not None:
                _store_probe(con, me, probe)
            if video_id and claim_id:
                # Only the claim it says it is rendering, and only while that
                # very claim still holds the video: a renderer that went idle
                # never keeps a lease alive (the worker's sweep re-queues an
                # orphan), and a heartbeat sent for an earlier claim of the
                # same video — delayed until the video was re-queued and
                # claimed again — never extends the claim that took over.
                con.execute(
                    "UPDATE videos SET render_lease_until = ? WHERE id = ? AND status = 'RENDERING' "
                    "AND renderer_id = ? AND render_claim_id = ? AND render_uploaded_at = '' "
                    "AND archived_at IS NULL",
                    (renderers.ts_add(now, renderers.LEASE_SECS), video_id, me, claim_id))
            # Stop instructions name a claim, not only a video, so the
            # renderer can tell "the render you reported" from a newer claim
            # of the same video it may have started since.
            stop = []
            if video_id:
                held = con.execute(
                    "SELECT 1 FROM videos WHERE id = ? AND status = 'RENDERING' AND renderer_id = ? "
                    "AND render_claim_id = ? AND archived_at IS NULL", (video_id, me, claim_id)).fetchone()
                if held is None:
                    stop.append({"video_id": video_id, "claim_id": claim_id})
            # Rows this renderer was holding that moved on without it
            # (archived, moved by a human, re-queued by lease expiry): stopped
            # too, and let go of so they are not listed again.
            for r in con.execute("SELECT id, render_claim_id FROM videos WHERE renderer_id = ? AND "
                                 "(status != 'RENDERING' OR archived_at IS NOT NULL)", (me,)).fetchall():
                entry = {"video_id": r["id"], "claim_id": r["render_claim_id"] or ""}
                if entry not in stop:
                    stop.append(entry)
            con.execute("UPDATE videos SET renderer_id = '', render_lease_until = '', render_claim_id = '' "
                        "WHERE renderer_id = ? AND status != 'RENDERING'", (me,))
            row = con.execute("SELECT * FROM renderers WHERE id = ?", (me,)).fetchone()
            credential, expires = renderers.maybe_rotate(con, me, now)
        requested = row["gpu_probe_requested_at"] or ""
        try:
            last_at = str((json.loads(row["gpu_probe"] or "null") or {}).get("at") or "")
        except (ValueError, AttributeError):
            last_at = ""
        needs_upgrade = reported_version != main
        if needs_upgrade:
            log.warning(f"gateway: renderer {me} runs {reported_version or 'an unknown version'}, "
                        f"main runs {main}: it needs an upgrade and gets no work")
        if stop:
            log.warning(f"gateway: renderer {me} told to stop {stop}")
        reply = {"enabled": bool(row["enabled"]), "needs_upgrade": needs_upgrade, "main_version": main,
                 "probe_now": bool(requested) and requested > last_at, "stop": stop,
                 "credential_expires_at": expires or row["credential_expires_at"] or ""}
        if credential:
            reply["credential"] = credential
            log.info(f"gateway: renderer {me} was issued a rotated credential")
        return jsonify(reply)

    # ── claim ────────────────────────────────────────────────────────────────

    def refuse(me, vid, status, comment, why) -> None:
        """Move a queued video out of the queue before anything is rendered,
        with its comment, guarded on it still being RENDER_QUEUED."""
        log.warning(f"[{vid}] claim by renderer {me}: refused, {status}: {why}", extra={"video_id": vid})
        with db.conn(db_path) as con:
            cur = con.execute("UPDATE videos SET status = ?, updated_at = ? WHERE id = ? AND status = 'RENDER_QUEUED'",
                              (status, db._now(), vid))
            if cur.rowcount:
                con.execute("INSERT INTO comments (video_id, author, content, created_at) VALUES (?, 'agent', ?, ?)",
                            (vid, render_results._truncate_comment(comment), db._now()))

    def pre_render_refusal(me, video) -> bool:
        """The checks a render used to make after its claim, made before it:
        a video refused here is never handed out. Same statuses and comments."""
        vid = video["id"]
        try:
            audio = tjobs.job_file(jobs_dir, vid, tjobs.AUDIO)
            timeline = tjobs.job_file(jobs_dir, vid, tjobs.TIMELINE)
            scene_config = tjobs.job_file(jobs_dir, vid, tjobs.SCENE_CONFIG)
            tjobs.images_dir(jobs_dir, vid)
            tjobs.output_file(output_dir, video["project_id"], vid)
        except tjobs.UnsafePath as e:
            # Not something a revision can fix, and retrying renders the same
            # refusal, so it goes straight to FAILED for a human to look at.
            refuse(me, vid, "FAILED",
                   f"Render refused, moved to FAILED: {e}. The video's id or its project's id "
                   "cannot be used as a file path, so nothing was staged or rendered.", str(e))
            return True
        missing = [
            name for name, written, p in [
                ("voice_file_path", video["voice_file_path"], audio),
                ("timeline_path", video["timeline_path"], timeline),
                ("scene_config_path", video["scene_config_path"], scene_config),
            ] if not written or not p.is_file()
        ]
        if missing:
            refuse(me, vid, "REVISION_REQUESTED", f"Render failed: missing job file(s): {missing}",
                   f"missing {missing}")
            return True
        cartoon = renderers.video_kind(video) == "cartoon_3d"
        mascot_id = video["mascot_id"] or ""
        # A Cartoon 3D video never carries a mascot: the API and the MCP server
        # refuse the pair and clear the mascot on a switch to the style. One
        # that holds both anyway is refused, rather than rendered without the
        # mascot a human chose. Neither a requeue nor the agent can fix it.
        if cartoon and mascot_id:
            refuse(me, vid, "FAILED",
                   f"Not rendered, moved to FAILED: this video is Cartoon 3D and also holds the mascot "
                   f"{mascot_id!r}. {tmascots.MASCOT_NOT_ON_CARTOON_3D} Create the video again.",
                   "Cartoon 3D with a mascot")
            return True
        if mascot_id:
            # The version pinned when the scenes were written, never the
            # mascot's current one. Neither a missing pin nor missing code is
            # something a requeue or the agent can fix.
            try:
                mascot_code(video)
            except tmascots.MascotError as e:
                refuse(me, vid, "FAILED",
                       f"Not rendered, moved to FAILED: this video has a mascot, and its drawing code cannot be "
                       f"staged: {e}. Create the video again.", str(e))
                return True
        return False

    def mascot_code(video) -> str:
        version = video["mascot_version"] or 0
        if version < 1:
            raise tmascots.MascotError(
                f"no version of mascot {video['mascot_id']!r} is pinned to this video (mascot_version is 0); "
                "the pin is written with the scene config")
        with db.conn(db_path) as con:
            return tmascots.code_for(con, remotion, video["mascot_id"], version)

    _VIDEO_COLS = ("id, project_id, updated_at, visual_style, resolved_renderer, mascot_id, mascot_version, "
                   "voice_file_path, timeline_path, scene_config_path, render_started_at, renderer_id, "
                   "render_claim_id, archived_at")
    # A renderer's unfinished claim: what it is rendering, until it uploads.
    _HELD = "status = 'RENDERING' AND renderer_id = ? AND render_uploaded_at = ''"

    def scheduler_inputs(con):
        queue = [_video_facts(jobs_dir, r) for r in con.execute(
            f"SELECT {_VIDEO_COLS} FROM videos WHERE status = 'RENDER_QUEUED' AND archived_at IS NULL "
            "ORDER BY updated_at, id")]
        busy = {}
        for r in con.execute(f"SELECT {_VIDEO_COLS} FROM videos WHERE status = 'RENDERING' "
                             "AND renderer_id != '' AND render_uploaded_at = ''"):
            v = _video_facts(jobs_dir, r)
            busy[v["renderer_id"]] = {"kind": renderers.video_kind(v), "frames": v["frames"],
                                      "started_at": v["render_started_at"]}
        rows = []
        for r in con.execute("SELECT * FROM renderers WHERE removed_at IS NULL"):
            d = dict(r)
            if d["id"] in busy:
                d["current"] = busy[d["id"]]
            rows.append(d)
        return queue, rows, renderers.recent_timings(con)

    def claim_reply(video, claim_id):
        kind = renderers.video_kind(video)
        return jsonify({
            "video_id": video["id"], "claim_id": claim_id, "kind": kind,
            "needs_gpu": renderers.requires_gpu(video), "cartoon": kind == "cartoon_3d",
            "mascot": bool(video["mascot_id"]), "total_frames": video["frames"] or 0,
            "lease_secs": renderers.LEASE_SECS,
            "settings": {"render_timeout_secs": render_results.render_timeout_secs(),
                         "render_stall_timeout_secs": render_results.render_stall_timeout_secs(),
                         "watermark": render_results.watermark_enabled()},
        })

    @app.post("/v1/claim")
    def claim_route():
        me = g.renderer["id"]
        main = current_version()
        for _ in range(MAX_CLAIM_ATTEMPTS):
            now = renderers.now_ts()
            with db.conn(db_path) as con:
                caller = con.execute("SELECT * FROM renderers WHERE id = ?", (me,)).fetchone()
                if caller is None or not caller["enabled"]:
                    log.warning(f"gateway: claim by renderer {me} refused: disabled")
                    return _err(409, "disabled")
                if renderers.needs_upgrade(caller, main):
                    log.warning(f"gateway: claim by renderer {me} refused: runs {caller['version']}, "
                                f"main runs {main}")
                    return _err(409, "needs_upgrade")
                held = con.execute(f"SELECT {_VIDEO_COLS} FROM videos WHERE {_HELD} "
                                   "ORDER BY render_started_at, id LIMIT 1", (me,)).fetchone()
                if held is not None:
                    if held["archived_at"] is not None:
                        # Archived while held: it can no longer be bundled or
                        # uploaded, and its lease is left to run out (the
                        # worker re-queues it); no second video before then.
                        return "", 204
                    # The renderer asked again while its claim is unfinished:
                    # its reply was lost, or it is confused. The same claim,
                    # never a second video — one render at a time.
                    con.execute("UPDATE videos SET render_lease_until = ? WHERE id = ? AND render_claim_id = ? "
                                f"AND {_HELD}", (renderers.ts_add(db._now(), renderers.LEASE_SECS), held["id"],
                                                 held["render_claim_id"], me))
                    log.info(f"[{held['id']}] renderer {me} claimed again; answered its unfinished claim",
                             extra={"video_id": held["id"]})
                    return claim_reply(_video_facts(jobs_dir, held), held["render_claim_id"])
                if caller["builtin"] and con.execute(
                        "SELECT 1 FROM settings WHERE key = ? AND value > ?",
                        (pipeline.RENDER_CLAIM_HOLD_KEY, db._now())).fetchone():
                    return "", 204
                queue, rows, timings = scheduler_inputs(con)
            vid = renderers.pick_video(queue, rows, timings, me, now, main)
            if vid is None:
                return "", 204
            video = next(v for v in queue if v["id"] == vid)
            if pre_render_refusal(me, video):
                continue
            stamp = db._now()
            claim_id = uuid.uuid4().hex
            hold = (" AND NOT EXISTS (SELECT 1 FROM settings WHERE key = ? AND value > ?)"
                    if caller["builtin"] else "")
            params = [me, claim_id, renderers.ts_add(stamp, renderers.LEASE_SECS), stamp, stamp, vid, me, me]
            if caller["builtin"]:
                params += [pipeline.RENDER_CLAIM_HOLD_KEY, stamp]
            # Guarded in the UPDATE's own WHERE clause (not SELECT-then-
            # compare): two renderers picking the same video cannot both get
            # it; one renderer cannot get a second video while it holds an
            # unfinished claim (two claims racing, or a retry after a lost
            # reply — the next pass answers the claim it holds); and the
            # built-in renderer's onboarding hold is in the same statement, so
            # onboarding (which writes the hold, then looks for a RENDERING
            # row) either sees this claim or prevents it.
            with db.conn(db_path) as con:
                cur = con.execute(
                    "UPDATE videos SET status = 'RENDERING', renderer_id = ?, render_claim_id = ?, "
                    "render_lease_until = ?, render_started_at = ?, render_uploaded_at = '', updated_at = ? "
                    "WHERE id = ? AND status = 'RENDER_QUEUED' AND archived_at IS NULL "
                    "AND EXISTS (SELECT 1 FROM renderers WHERE id = ? AND enabled = 1 AND removed_at IS NULL) "
                    f"AND NOT EXISTS (SELECT 1 FROM videos WHERE {_HELD})" + hold, params)
            if cur.rowcount != 1:
                continue
            log.info(f"[{vid}] claimed by renderer {me} ({renderers.video_kind(video)})",
                     extra={"video_id": vid})
            return claim_reply(video, claim_id)
        return "", 204

    # ── jobs ─────────────────────────────────────────────────────────────────

    def request_claim():
        """The claim id the request names (X-Render-Claim), or ''."""
        return request.headers.get(CLAIM_HEADER, "").strip()[:64]

    def held_video(vid):
        """The video (as _video_facts) when the caller holds the claim the
        request names: RENDERING, its renderer_id, that render_claim_id, not
        archived. Else None."""
        claim_id = request_claim()
        if not claim_id:
            return None
        with db.conn(db_path) as con:
            row = con.execute(
                f"SELECT {_VIDEO_COLS} FROM videos WHERE id = ? AND status = 'RENDERING' "
                "AND renderer_id = ? AND render_claim_id = ? AND archived_at IS NULL",
                (vid, g.renderer["id"], claim_id)).fetchone()
        return _video_facts(jobs_dir, row) if row else None

    def bundle_members(video) -> list:
        vid = video["id"]
        try:
            job = tjobs.job_dir(jobs_dir, vid)
            members = []
            for name in tjobs.JOB_FILES:
                p = tjobs.job_file(jobs_dir, vid, name)
                if not _is_plain_file(p):
                    raise BundleUnavailable(f"{name} is missing")
                members.append((name, p))
            members += _plain_files(tjobs.images_dir(jobs_dir, vid), tjobs.IMAGES)
            source = tjobs.join_below(job, *CARTOON_SOURCE)
            if _is_plain_file(source):
                members.append(("/".join(CARTOON_SOURCE), source))
            mix = tjobs.join_below(job, *CARTOON_MIX)
            audio = tjobs.job_file(jobs_dir, vid, tjobs.AUDIO)
            # a re-voiced video makes an older mix stale: the voice alone is muxed then
            if _is_plain_file(mix) and mix.stat().st_mtime >= audio.stat().st_mtime:
                members.append(("/".join(CARTOON_MIX), mix))
            if video["mascot_id"]:
                try:
                    members.append((MASCOT_MEMBER, mascot_code(video).encode("utf-8")))
                except tmascots.MascotError as e:
                    raise BundleUnavailable(f"the mascot's drawing code cannot be staged: {e}") from None
            try:
                tree = tjobs.scene_dir(generated, vid)
            except tjobs.UnsafePath as e:
                raise BundleUnavailable(f"the generated scenes cannot be bundled: {e}") from None
            members += _plain_files(tree, f"scenes/{vid}")
            for name in _flat_scene_names(tjobs.job_file(jobs_dir, vid, tjobs.SCENE_CONFIG)):
                try:
                    flat = tjobs.scene_file(generated, "", name)
                except tjobs.UnsafePath:
                    continue
                if _is_plain_file(flat):
                    members.append((f"scenes/{FLAT_SCENES}/{name}.tsx", flat))
            return members
        except tjobs.UnsafePath as e:
            raise BundleUnavailable(str(e)) from None
        except OSError as e:
            raise BundleUnavailable(f"the job's files cannot be read: {e}") from None

    @app.get("/v1/jobs/<video_id>/bundle")
    def bundle_route(video_id):
        video = held_video(video_id)
        if video is None:
            log.warning(f"[{video_id}] bundle refused: {_who()} does not hold its lease", extra={"video_id": video_id})
            return _err(403, "not_lease_holder")
        try:
            members = bundle_members(video)
        except BundleUnavailable as e:
            log.warning(f"[{video_id}] bundle for renderer {g.renderer['id']} unavailable: {e}",
                        extra={"video_id": video_id})
            return _err(409, "bundle_unavailable", detail=str(e))
        return Response(_stream_tar(members), mimetype="application/x-tar",
                        headers={"Content-Disposition": f'attachment; filename="{video_id}.tar"'})

    # Uploads streaming now, claim id -> its temp file's name: one per claim,
    # MAX_CONCURRENT_UPLOADS in all. Admission happens before the body is
    # read or a temp file made, so neither a renderer retrying an upload that
    # is still streaming nor many claims at once can multiply what the disk
    # holds in flight.
    uploads_lock = threading.Lock()
    uploading = {}

    def free_bytes() -> int:
        return shutil.disk_usage(output_dir).free

    def insufficient_storage(video_id, me, free, need):
        log.warning(f"[{video_id}] upload from renderer {me} refused: {free} bytes free on the output "
                    f"filesystem, {need} needed to keep {MIN_FREE_BYTES} free", extra={"video_id": video_id})
        return _err(507, "insufficient_storage", min_free_bytes=MIN_FREE_BYTES)

    @app.put("/v1/jobs/<video_id>/output")
    def output_route(video_id):
        video = held_video(video_id)
        if video is None:
            log.warning(f"[{video_id}] upload refused: {_who()} does not hold its lease", extra={"video_id": video_id})
            return _err(403, "not_lease_holder")
        me, claim_id = g.renderer["id"], request_claim()
        limit = MAX_OUTPUT_BYTES
        declared = request.content_length
        if declared is not None and declared > limit:
            log.warning(f"[{video_id}] upload from renderer {me} refused: {declared} bytes "
                        f"is over the {limit}-byte limit", extra={"video_id": video_id})
            return _err(413, "output_too_large", limit=limit)
        with uploads_lock:
            if claim_id in uploading:
                log.warning(f"[{video_id}] upload from renderer {me} refused: an upload for this claim is "
                            "still streaming", extra={"video_id": video_id})
                return _err(409, "upload_in_progress")
            if len(uploading) >= MAX_CONCURRENT_UPLOADS:
                log.warning(f"[{video_id}] upload from renderer {me} refused: {len(uploading)} uploads "
                            "already streaming", extra={"video_id": video_id})
                return _busy()
            # The name is chosen here, under the lock, so the sweep below
            # (and any other admission's) knows it is being written.
            # (No video id in it: a long id leaves no room in a file name.)
            tmp_name = f"{uuid.uuid4().hex}{UPLOAD_SUFFIX}"
            uploading[claim_id] = tmp_name
            live = set(uploading.values())
        try:
            _sweep_uploads(output_dir, live=live, older_than=UPLOAD_ORPHAN_SECS)
            return receive_output(video, video_id, me, claim_id, limit, declared, tmp_name)
        finally:
            with uploads_lock:
                uploading.pop(claim_id, None)

    def receive_output(video, video_id, me, claim_id, limit, declared, tmp_name):
        try:
            free = free_bytes()
        except OSError as e:
            return _err(500, "upload_failed", detail=str(e))
        if free - (declared or 0) < MIN_FREE_BYTES:
            return insufficient_storage(video_id, me, free, (declared or 0) + MIN_FREE_BYTES)
        try:
            out = tjobs.output_file(output_dir, video["project_id"], video_id)
        except tjobs.UnsafePath as e:
            return _err(409, "unsafe_path", detail=str(e))
        try:
            tmp_dir = _upload_dir(output_dir)
            out.parent.mkdir(parents=True, exist_ok=True)
        except (tjobs.UnsafePath, OSError) as e:
            log.warning(f"[{video_id}] upload from renderer {me} failed: {e}", extra={"video_id": video_id})
            return _err(500, "upload_failed", detail=str(e))
        tmp = tmp_dir / tmp_name
        written = 0
        next_check = DISK_CHECK_BYTES
        try:
            # O_EXCL | O_NOFOLLOW: a fresh file of our own, never one planted
            # under the name (nor a link) — the directory is in a bind mount.
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o666)
            with os.fdopen(fd, "wb") as fh:
                while True:
                    chunk = _read_chunk(request.stream, CHUNK_BYTES)
                    if not chunk:
                        break
                    written += len(chunk)
                    if written > limit:
                        # A chunked (or lying) body: counted as it arrives,
                        # never trusted to end. The temp file goes below.
                        log.warning(f"[{video_id}] upload from renderer {me} aborted: over the "
                                    f"{limit}-byte limit", extra={"video_id": video_id})
                        return _err(413, "output_too_large", limit=limit)
                    if written >= next_check:
                        next_check = written + DISK_CHECK_BYTES
                        free = free_bytes()
                        if free < MIN_FREE_BYTES:
                            # The temp file goes below.
                            return insufficient_storage(video_id, me, free, MIN_FREE_BYTES)
                    fh.write(chunk)
                fh.flush()
                os.fsync(fh.fileno())
            # The lease may have run out while the body streamed, and another
            # claim (another renderer, or this one again) uploaded since: the
            # claim is checked again, and the rename made, inside one write
            # transaction, so no claim can change hands between the two.
            with db.conn(db_path) as con:
                con.execute("BEGIN IMMEDIATE")
                still = con.execute(
                    "SELECT 1 FROM videos WHERE id = ? AND status = 'RENDERING' AND renderer_id = ? "
                    "AND render_claim_id = ? AND render_uploaded_at = '' AND archived_at IS NULL",
                    (video_id, me, claim_id)).fetchone()
                if still is None:
                    log.warning(f"[{video_id}] upload from renderer {me} discarded: its claim was lost while "
                                "it uploaded", extra={"video_id": video_id})
                    return _err(409, "claim_lost")
                os.replace(tmp, out)
        except _BodyUnread as e:
            # A stalled (or abandoned) upload: the temp file goes below and
            # the claim's slot is released by the caller, so the renderer
            # can try again at once.
            return _body_unread(e, f"the rest of its upload ({written} bytes received)")
        except OSError as e:
            log.warning(f"[{video_id}] upload from renderer {me} failed: {e}",
                        extra={"video_id": video_id})
            return _err(500, "upload_failed", detail=str(e))
        finally:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
        log.info(f"[{video_id}] output uploaded by renderer {me}: {written} bytes",
                 extra={"video_id": video_id})
        return jsonify({"bytes": written})

    @app.post("/v1/jobs/<video_id>/result")
    def result_route(video_id):
        me, claim_id = g.renderer["id"], request_claim()
        video = held_video(video_id)
        if video is None:
            log.warning(f"[{video_id}] late result from renderer {me} dropped: it does not hold the lease",
                        extra={"video_id": video_id})
            return _err(403, "not_lease_holder")
        body = _body()
        outcome = body.get("outcome")
        if outcome not in OUTCOMES:
            return _err(400, "bad_outcome", detail=f"outcome must be one of {list(OUTCOMES)}")
        error = _str(body.get("error"), 20000)
        on_gpu = body.get("on_gpu") is True
        gpu_ok = body.get("gpu_ok") if isinstance(body.get("gpu_ok"), bool) else None
        kind = renderers.video_kind(video)
        if outcome == "success":
            try:
                out = tjobs.output_file(output_dir, video["project_id"], video_id)
                ok = _is_plain_file(out) and out.stat().st_size > 0
            except (tjobs.UnsafePath, OSError):
                ok = False
            if ok:
                stamp = db._now()
                with db.conn(db_path) as con:
                    cur = con.execute(
                        "UPDATE videos SET video_path = ?, render_uploaded_at = ?, renderer_id = '', "
                        "render_lease_until = '', render_claim_id = '', updated_at = ? WHERE id = ? "
                        "AND status = 'RENDERING' AND renderer_id = ? AND render_claim_id = ?",
                        (str(out), stamp, stamp, video_id, me, claim_id))
                    if cur.rowcount != 1:
                        return _err(403, "not_lease_holder")
                    frames, seconds = body.get("frames"), body.get("seconds")
                    if (isinstance(frames, int) and not isinstance(frames, bool) and frames > 0
                            and isinstance(seconds, (int, float)) and not isinstance(seconds, bool)
                            and seconds > 0):
                        con.execute("INSERT INTO render_timings (renderer_id, kind, on_gpu, frames, seconds, "
                                    "created_at) VALUES (?, ?, ?, ?, ?, ?)",
                                    (me, kind, 1 if on_gpu else 0, frames, float(seconds), stamp))
                log.info(f"[{video_id}] rendered by renderer {me}; waiting for the review",
                         extra={"video_id": video_id})
                return jsonify({})
            log.warning(f"[{video_id}] renderer {me} reported success with no uploaded output",
                        extra={"video_id": video_id})
            outcome, error = "error", "output missing: the renderer reported success but no mp4 was uploaded"
        if gpu_ok is False:
            # The renderer's own re-test says its GPU stopped working: no more
            # GPU work for it until a probe passes (its next heartbeat carries
            # the probe; one sent with the result is stored now).
            with db.conn(db_path) as con:
                probe = body.get("gpu_probe")
                if isinstance(probe, dict):
                    _store_probe(con, me, probe)
                con.execute("UPDATE renderers SET gpu_verified = 0 WHERE id = ?", (me,))
        retry_status = "REVISION_REQUESTED" if outcome == "failed" else "RENDER_QUEUED"
        if not error:
            error = {"failed": "the render failed with no error output", "stalled": "Render stalled",
                     "timeout": "Render timed out", "error": "The renderer hit an error"}[outcome]
        log.warning(f"[{video_id}] renderer {me} reported {outcome}: {error[-300:]}", extra={"video_id": video_id})
        # Routed only while this claim still holds the video: one guarded
        # transaction (render_results._claim_guard), so a lease that ran out
        # after the check above, and a claim that took the video over since,
        # are never touched by this stale result. It releases the claim too.
        if not render_results.after_render_failure(video_id, error, retry_status, on_gpu,
                                                   renderers.requires_gpu(video), kind == "cartoon_3d", gpu_ok,
                                                   claim=(me, claim_id)):
            log.warning(f"[{video_id}] result from renderer {me} changed nothing: its claim was lost first",
                        extra={"video_id": video_id})
        return jsonify({})

    return app


def _store_probe(con, renderer_id, probe: dict) -> None:
    """A renderer's GPU probe, in the same JSON shape the single-renderer
    probe row had. gpu_verified is exactly probe["ok"] is True. A pending
    dashboard request the probe answers (it started after the request) is
    cleared."""
    con.execute("UPDATE renderers SET gpu_probe = ?, gpu_verified = ? WHERE id = ?",
                (json.dumps(probe), 1 if probe.get("ok") is True else 0, renderer_id))
    at = str(probe.get("at") or "")
    if at:
        con.execute("UPDATE renderers SET gpu_probe_requested_at = '' WHERE id = ? "
                    "AND gpu_probe_requested_at != '' AND gpu_probe_requested_at <= ?", (renderer_id, at))


def tls_context(secrets_dir=None) -> ssl.SSLContext:
    """The gateway's server TLS context from the render_tls_key/_cert secret
    files. Raises SecretMissing when either is absent or empty."""
    read_secret(TLS_KEY_NAME, secrets_dir)
    read_secret(TLS_CERT_NAME, secrets_dir)
    d = Path(secrets_dir) if secrets_dir is not None else default_secrets_dir()
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.load_cert_chain(certfile=str(d / TLS_CERT_NAME), keyfile=str(d / TLS_KEY_NAME))
    return ctx


class _BoundedReader:
    """A connection's read side (the handler's rfile) with time bounds.

    The socket timeout alone bounds one read, not a request: a client that
    sends a byte just inside it, again and again, would hold the thread for
    ever. So every read here is made of single reads of what has arrived
    (read1/peek), each under a socket timeout of the idle bound or what is
    left of the current deadline, whichever is less:
    - `deadline` (monotonic): a read past it raises TimeoutError (the
      request head; a JSON body).
    - `eof_at` (monotonic): a read past it is end of input — set once the
      reply is out, so werkzeug's drain of an unread body ends quietly.
    After a read timed out the connection is done: later reads are end of
    input (a socket file refuses every read after a timeout anyway)."""

    def __init__(self, raw, sock, idle: float):
        self._f = raw
        self._sock = sock
        self.idle = idle
        self.deadline = None
        self.eof_at = None
        self._dead = False

    def _arm(self) -> bool:
        """Set the socket timeout for the next read. False = end of input."""
        if self._dead:
            return False
        now = time.monotonic()
        if self.eof_at is not None and now >= self.eof_at:
            return False
        if self.deadline is not None and now >= self.deadline:
            self._dead = True
            raise TimeoutError("the request did not arrive in time")
        limit = self.idle
        for t in (self.deadline, self.eof_at):
            if t is not None:
                limit = min(limit, t - now)
        self._sock.settimeout(max(limit, 0.01))
        return True

    def _one(self, op, *args):
        try:
            return op(*args)
        except TimeoutError:
            self._dead = True
            raise

    def read1(self, n: int = -1) -> bytes:
        if not self._arm():
            return b""
        return self._one(self._f.read1, n if n is not None and n >= 0 else 1 << 16)

    def read(self, n: int = -1) -> bytes:
        out = bytearray()
        while n is None or n < 0 or len(out) < n:
            want = (1 << 16) if n is None or n < 0 else n - len(out)
            chunk = self.read1(want)
            if not chunk:
                break
            out += chunk
        return bytes(out)

    def readinto(self, b) -> int:
        chunk = self.read1(len(b))
        b[:len(chunk)] = chunk
        return len(chunk)

    def readline(self, limit: int = -1) -> bytes:
        out = bytearray()
        while limit is None or limit < 0 or len(out) < limit:
            if not self._arm():
                break
            data = self._one(self._f.peek, 1)
            if not data:
                break
            want = len(data) if limit is None or limit < 0 else min(len(data), limit - len(out))
            nl = data.find(b"\n", 0, want)
            if nl >= 0:
                want = nl + 1
            out += self._f.read(want)         # already buffered: no socket read
            if nl >= 0:
                break
        return bytes(out)

    def reply_started(self, drain_secs: float) -> None:
        """The reply is going out: no body deadline any more, writes get the
        idle bound, and what is left of an unread body gets `drain_secs`."""
        self.deadline = None
        self.eof_at = time.monotonic() + drain_secs
        self._sock.settimeout(self.idle)

    def __getattr__(self, name):
        return getattr(self._f, name)


def _handler_class():
    from werkzeug.serving import WSGIRequestHandler

    class _GatewayRequestHandler(WSGIRequestHandler):
        """werkzeug's handler with the gateway's time bounds. `timeout` is
        what socketserver's StreamRequestHandler.setup applies as the
        connection's socket timeout; the TLS handshake is made here, in the
        connection's own thread under REQUEST_HEAD_SECS, instead of in the
        server's accept loop, where a client that never finishes it would
        stop every other connection from being accepted."""

        timeout = GATEWAY_IDLE_TIMEOUT_SECS

        def setup(self):
            super().setup()
            self.rfile = _BoundedReader(self.rfile, self.connection, self.timeout)
            self.rfile.deadline = time.monotonic() + REQUEST_HEAD_SECS

        def handle(self):
            if isinstance(self.connection, ssl.SSLSocket):
                try:
                    # do_handshake's timeout covers the whole handshake.
                    self.connection.settimeout(max(self.rfile.deadline - time.monotonic(), 0.01))
                    self.connection.do_handshake()
                except (OSError, ValueError):
                    return
            super().handle()

        def make_environ(self):
            environ = super().make_environ()
            environ[READER_KEY] = self.rfile
            environ[RELEASE_KEY] = []
            return environ

        def run_wsgi(self):
            # The head has arrived; the route sets its body's bound (or none,
            # for an upload), and writes get the idle bound.
            self.rfile.deadline = None
            self.connection.settimeout(self.timeout)
            try:
                super().run_wsgi()
            finally:
                # werkzeug closes the response only when its drain ended
                # without an error: a client that reset the connection
                # mid-drain would otherwise keep its renderer's count for
                # ever. A release already made is not made twice.
                _release(getattr(self, "environ", None))

    return _GatewayRequestHandler


def _release(environ) -> None:
    """Give back the per-renderer counts a request is holding (RELEASE_KEY)."""
    for release in (environ or {}).get(RELEASE_KEY) or ():
        release()


def _bounded_app(app):
    """The gateway app, wrapped so that once a reply starts, the connection's
    reader gives werkzeug's drain of an unread body DRAIN_SECS, and a body
    deadline a route left behind no longer applies; and so that a request's
    per-renderer count is released only when werkzeug closes the response,
    which it does after sending all of it (a bundle streams after the
    request's teardown) and after draining an unread body — or at once when
    the app fails before there is a response to close."""
    from werkzeug.wsgi import ClosingIterator

    def wsgi(environ, start_response):
        reader = environ.get(READER_KEY)
        environ.setdefault(RELEASE_KEY, [])

        def started(status, headers, exc_info=None):
            if reader is not None:
                reader.reply_started(DRAIN_SECS)
            return start_response(status, headers, exc_info)
        try:
            body = app(environ, started)
        except BaseException:
            _release(environ)
            raise
        return ClosingIterator(body, lambda: _release(environ))
    return wsgi


def _server_class():
    from werkzeug.serving import ThreadedWSGIServer

    class _GatewayServer(ThreadedWSGIServer):
        """werkzeug's threaded server with MAX_CONNECTIONS: a slot is taken
        when a connection is accepted, before its thread is made, and given
        back when that thread ends (the connection closed). With no slot the
        connection is closed at once and no thread is made."""

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.connection_slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
            self._refused_logged = None

        def process_request(self, request, client_address):
            if not self.connection_slots.acquire(blocking=False):
                # Logged at most once a minute: a flood would fill the log.
                now = time.monotonic()
                if self._refused_logged is None or now - self._refused_logged >= 60:
                    self._refused_logged = now
                    log.warning(f"gateway: a connection refused: {MAX_CONNECTIONS} connections are "
                                "already open")
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, client_address)
            except BaseException:
                # No thread started (socketserver closes the connection).
                self.connection_slots.release()
                raise

        def process_request_thread(self, request, client_address):
            try:
                super().process_request_thread(request, client_address)
            finally:
                self.connection_slots.release()

    return _GatewayServer


def make_gateway_server(app, host: str, port: int, secrets_dir=None):
    """A threaded werkzeug server for the gateway over TLS, not yet serving
    (the caller runs serve_forever in a thread), holding at most
    MAX_CONNECTIONS connections. None, with an error logged, when the TLS
    pair is missing or cannot be loaded: the API must still serve the
    dashboard.

    The listening socket is wrapped here rather than by werkzeug, with
    do_handshake_on_connect=False, so the handshake happens in each
    connection's thread under its time bound (see _handler_class)."""
    try:
        ctx = tls_context(secrets_dir)
    except SecretMissing as e:
        log.error(f"render gateway not started: its TLS key or certificate is missing ({e}). "
                  "Renderers cannot reach the API until the secrets exist "
                  "(python3 -m tubematic_core.auth ensure) and the API is restarted.")
        return None
    except (ssl.SSLError, ValueError, OSError) as e:
        # Both files are there but are not a usable pair (a key and a
        # certificate restored from different backups, a truncated file).
        # Never replaced here: a new certificate is a new pin.
        log.error(f"render gateway not started: its TLS key and certificate cannot be used as a pair ({e}). "
                  "The API still serves the dashboard, but no renderer, the built-in one included, can "
                  "reach it. To recover, restore render_tls_key and render_tls_cert together from the same "
                  "backup (the certificate pin stays the same), or delete both and run "
                  "python3 scripts/service.py start to make a new pair, which changes the pin: every remote "
                  "renderer must then be enrolled again with a new token. Then restart tubematic-api and "
                  "tubematic-renderer.")
        return None
    server = _server_class()(host, port, _bounded_app(app), _handler_class())
    server.socket = ctx.wrap_socket(server.socket, server_side=True, do_handshake_on_connect=False)
    # werkzeug reads it for the environ's https scheme and its SSL error log
    server.ssl_context = ctx
    return server
