"""Staging and installing external style packages (TMDEV-253).

An install has two halves. Staging fetches a package (a zip, a git repository at
a pinned commit or tag, a gallery entry, a folder an agent dropped into
`styles-incoming/`, or an installed package that waits for review), unpacks it
into `styles-pending/<pending id>/package/`, checks it like the registry does,
scans it (style_scan.py) and writes `pending.json`. Anyone with the API or MCP
token can stage. Confirming copies the staged package into the styles folder
and records its approval (external_styles.INSTALLED); the API accepts that only
with the dashboard password, so the yes is always a person's.

A staged package expires after PENDING_HOURS. Nothing here touches the
database: the API refuses a removal while a video or domain uses the style.
"""
import contextlib
import datetime as _dt
import fcntl
import hashlib
import io
import json
import os
import pathlib
import re
import secrets
import shutil
import stat
import subprocess
import urllib.parse
import urllib.request
import zipfile

from . import external_styles as ext
from . import jobfiles
from . import style_scan

PENDING_DIR = pathlib.Path(os.environ.get("TUBEMATIC_STYLES_PENDING_DIR", "/styles-pending"))
INCOMING_DIR = pathlib.Path(os.environ.get("TUBEMATIC_STYLES_INCOMING_DIR", "/styles-incoming"))
PENDING_HOURS = 24
MAX_PENDING = 20
MAX_ZIP_BYTES = 25_000_000
MAX_UNPACKED_BYTES = 60_000_000
MAX_FILES = 2000
MAX_INDEX_BYTES = 2_000_000
GIT_TIMEOUT_SECS = 120
HTTP_TIMEOUT_SECS = 30
PENDING_FILE = "pending.json"
# The curated gallery's index (TMDEV-255). Only a package from this index is
# marked reviewed: style_gallery_url can be pointed anywhere by anything with
# the API token, and someone else's index is not the maintainer's review.
OFFICIAL_GALLERY_URL = "https://teja156.github.io/tubematic-styles/index.json"
PID_RE = re.compile(r"[0-9a-f]{16}")
REF_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}")
INCOMING_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,80}")
# what a zip or a repository may carry beside the package and is dropped before the check
_DROPPED = re.compile(r"^(\.git|\.github|\.gitignore|\.gitattributes|\.DS_Store|__MACOSX)$")


class InstallError(Exception):
    """A refusal, worded for the person or agent that asked."""


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0)


def _iso(t: _dt.datetime) -> str:
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: str) -> _dt.datetime | None:
    try:
        return _dt.datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=_dt.timezone.utc)
    except (TypeError, ValueError):
        return None


@contextlib.contextmanager
def _lock():
    """One install, removal or staging at a time across the API and MCP processes."""
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    with open(PENDING_DIR / ".lock", "w") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        yield


def _owned_like(path: pathlib.Path, ref: pathlib.Path) -> None:
    """The containers run as root; files they write in the data folder are given
    to its owner, so the person can still delete them without sudo."""
    if os.geteuid() != 0:
        return
    try:
        st = os.stat(ref)
    except OSError:
        return
    for top, dirs, files in os.walk(path):
        for name in [top, *(os.path.join(top, n) for n in dirs + files)]:
            with contextlib.suppress(OSError):
                os.lchown(name, st.st_uid, st.st_gid)


# ── Fetching ────────────────────────────────────────────────────────────────

class _HttpsOnlyRedirect(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only to another https address: the first address is
    checked, and a redirect must not lead to plain http or an internal service."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urllib.parse.urlsplit(newurl).scheme != "https":
            raise InstallError(f"{req.full_url} redirected to a non-https address, {newurl}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


_opener = urllib.request.build_opener(_HttpsOnlyRedirect)


def _http_get(url: str, cap: int) -> bytes:
    """GET an https URL, refusing a body over cap bytes."""
    if urllib.parse.urlsplit(url).scheme != "https":
        raise InstallError(f"{url} is not an https address")
    req = urllib.request.Request(url, headers={"User-Agent": "tubematic-style-install"})
    try:
        with _opener.open(req, timeout=HTTP_TIMEOUT_SECS) as resp:
            body = resp.read(cap + 1)
    except OSError as exc:
        raise InstallError(f"{url} could not be downloaded: {exc}") from exc
    if len(body) > cap:
        raise InstallError(f"{url} is larger than {cap // 1_000_000} MB")
    return body


def gallery_index(index_url: str) -> list[dict]:
    """The gallery's entries: [{id, name, author, tagline, version, archive_url, sha256, ...}]."""
    try:
        data = json.loads(_http_get(index_url, MAX_INDEX_BYTES))
    except ValueError as exc:
        raise InstallError(f"the gallery index at {index_url} is not valid JSON") from exc
    styles = data.get("styles") if isinstance(data, dict) else None
    if not isinstance(styles, list):
        raise InstallError(f"the gallery index at {index_url} has no styles list")
    return [s for s in styles if isinstance(s, dict) and isinstance(s.get("id"), str)
            and ext.ID_RE.fullmatch(s["id"])]


def _unzip(data: bytes, dest: pathlib.Path) -> None:
    if len(data) > MAX_ZIP_BYTES:
        raise InstallError(f"the zip is larger than {MAX_ZIP_BYTES // 1_000_000} MB")
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as exc:
        raise InstallError("the file is not a zip archive") from exc
    # directory entries count too: each one is a mkdir
    if len(zf.infolist()) > MAX_FILES:
        raise InstallError(f"the zip holds more than {MAX_FILES} entries")
    infos = [i for i in zf.infolist() if not i.is_dir()]
    if len(infos) > MAX_FILES:
        raise InstallError(f"the zip holds more than {MAX_FILES} files")
    if sum(i.file_size for i in infos) > MAX_UNPACKED_BYTES:
        raise InstallError(f"the zip unpacks to more than {MAX_UNPACKED_BYTES // 1_000_000} MB")
    for info in infos:
        name = info.filename
        parts = pathlib.PurePosixPath(name).parts
        if name.startswith("/") or "\\" in name or ".." in parts or not parts:
            raise InstallError(f"the zip holds {name!r}, a path outside the package")
        if stat.S_ISLNK(info.external_attr >> 16):
            raise InstallError(f"the zip holds a symlink, {name!r}; a style package holds plain files only")
        target = dest.joinpath(*parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info) as src, open(target, "wb") as out:
            shutil.copyfileobj(src, out)


# https only: a file:// or ssh:// address would reach the container's own files or keys
_GIT_PROTOCOL = ["-c", "protocol.allow=never", "-c", "protocol.https.allow=always"]


def _check_git_source(url: str, ref: str) -> None:
    split = urllib.parse.urlsplit(url)
    if split.scheme != "https" or not split.hostname or "@" in split.netloc:
        raise InstallError("a repository address must be https://host/owner/repo, with no user name or token in it")
    if not REF_RE.fullmatch(ref or "") or ".." in ref:
        raise InstallError("name a commit or a tag to install, so the code you review is the code that runs")


def _git(url: str, ref: str, dest: pathlib.Path) -> str:
    env = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "HOME": str(dest.parent),
           "GIT_TERMINAL_PROMPT": "0", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": os.devnull}
    base = ["git", *_GIT_PROTOCOL, "-c", "core.symlinks=false"]

    def run(*args):
        try:
            proc = subprocess.run([*base, *args], cwd=dest, env=env, capture_output=True, text=True,
                                  timeout=GIT_TIMEOUT_SECS)
        except FileNotFoundError as exc:
            raise InstallError("git is not installed in this container") from exc
        except subprocess.TimeoutExpired as exc:
            raise InstallError(f"git did not finish within {GIT_TIMEOUT_SECS} s") from exc
        if proc.returncode:
            raise InstallError(f"git {args[0]} failed: {(proc.stderr or proc.stdout).strip()[-300:]}")
        return proc.stdout.strip()

    dest.mkdir(parents=True, exist_ok=True)
    run("init", "-q")
    run("fetch", "-q", "--depth", "1", "--no-tags", url, ref)
    run("checkout", "-q", "FETCH_HEAD")
    commit = run("rev-parse", "FETCH_HEAD")
    shutil.rmtree(dest / ".git")
    return commit


def _package_root(d: pathlib.Path) -> pathlib.Path:
    """The folder holding style.json: d itself, or the one folder a zip wraps it in."""
    for entry in list(d.iterdir()):
        if _DROPPED.match(entry.name):
            shutil.rmtree(entry) if entry.is_dir() and not entry.is_symlink() else entry.unlink()
    if (d / "style.json").is_file():
        return d
    inner = [e for e in d.iterdir()]
    if len(inner) == 1 and inner[0].is_dir() and not inner[0].is_symlink() and (inner[0] / "style.json").is_file():
        return _package_root(inner[0])
    raise InstallError("no style.json at the top of the package (or inside its one top folder)")


# ── Staging ─────────────────────────────────────────────────────────────────

def _pending_dir(pid: str) -> pathlib.Path:
    if not PID_RE.fullmatch(pid or ""):
        raise InstallError("no such pending install")
    return PENDING_DIR / pid


def sweep(now: _dt.datetime | None = None) -> None:
    """Remove pending installs that expired or were never finished."""
    now = now or _now()
    if not PENDING_DIR.is_dir():
        return
    for entry in PENDING_DIR.iterdir():
        if not PID_RE.fullmatch(entry.name) or not entry.is_dir():
            continue
        try:
            rec = json.loads((entry / PENDING_FILE).read_text(encoding="utf-8"))
            expires = _parse(rec.get("expires_at"))
        except (OSError, ValueError, AttributeError):
            expires = None
            with contextlib.suppress(OSError):
                if now.timestamp() - entry.stat().st_mtime < 3600:  # still being staged
                    continue
        if expires is None or expires <= now:
            shutil.rmtree(entry, ignore_errors=True)


def stage(source: dict, *, index_url: str = "") -> dict:
    """Fetch, check and scan a package; returns the pending record. Raises InstallError."""
    kind = source.get("kind")
    if kind not in ("zip", "git", "gallery", "incoming", "installed"):
        raise InstallError("source.kind must be zip, git, gallery, incoming or installed")
    with _lock():
        sweep()
        if sum(1 for e in PENDING_DIR.iterdir() if PID_RE.fullmatch(e.name)) >= MAX_PENDING:
            raise InstallError(f"{MAX_PENDING} installs are already waiting: confirm or discard some first")
        pid = secrets.token_hex(8)
        work = PENDING_DIR / pid
        work.mkdir()
        try:
            return _stage_into(work, pid, kind, source, index_url)
        except BaseException:
            shutil.rmtree(work, ignore_errors=True)
            raise


def _stage_into(work: pathlib.Path, pid: str, kind: str, source: dict, index_url: str) -> dict:
    raw = work / "raw"
    raw.mkdir()
    origin = {"kind": kind}
    reviewed = False
    if kind == "zip":
        data = source.get("data")
        if not isinstance(data, (bytes, bytearray)) or not data:
            raise InstallError("the upload is empty")
        origin.update(filename=str(source.get("filename") or "upload.zip")[:200],
                      sha256=hashlib.sha256(data).hexdigest())
        _unzip(bytes(data), raw)
    elif kind == "git":
        url, ref = str(source.get("url") or "").strip(), str(source.get("ref") or "").strip()
        _check_git_source(url, ref)
        origin.update(url=url, ref=ref, commit=_git(url, ref, raw))
    elif kind == "gallery":
        gid = str(source.get("id") or "")
        if not index_url:
            raise InstallError("no gallery address is set (setting style_gallery_url)")
        entry = next((s for s in gallery_index(index_url) if s["id"] == gid), None)
        if entry is None:
            raise InstallError(f"the gallery has no style {gid!r}")
        data = _http_get(str(entry.get("archive_url") or ""), MAX_ZIP_BYTES)
        if hashlib.sha256(data).hexdigest() != entry.get("sha256"):
            raise InstallError("the downloaded archive does not match the gallery's checksum; nothing was installed")
        origin.update(gallery_id=gid, url=entry.get("archive_url"), sha256=entry["sha256"],
                      commit=entry.get("commit", ""), index=index_url)
        reviewed = bool(OFFICIAL_GALLERY_URL) and index_url == OFFICIAL_GALLERY_URL
        _unzip(data, raw)
    elif kind == "incoming":
        name = str(source.get("name") or "")
        if not INCOMING_NAME_RE.fullmatch(name):
            raise InstallError("name a folder or .zip directly inside styles-incoming/")
        src = INCOMING_DIR / name
        if src.is_symlink() or not src.exists():
            raise InstallError(f"styles-incoming/{name} does not exist (or is a symlink)")
        origin.update(name=name)
        if src.is_file():
            if src.stat().st_size > MAX_ZIP_BYTES:
                raise InstallError(f"the zip is larger than {MAX_ZIP_BYTES // 1_000_000} MB")
            _unzip(src.read_bytes(), raw)
        else:
            _copy_tree(src, raw / "pkg")
    else:  # installed: a valid package that waits for review
        sid = str(source.get("id") or "")
        found = ext.load(ext.STYLES_DIR).get(sid)
        if not found:
            raise InstallError(f"no installed style {sid!r}")
        origin.update(installed=sid)
        _copy_tree(found.path, raw / "pkg")

    root = _package_root(raw)
    package = work / "package"
    os.replace(root, package)
    shutil.rmtree(raw, ignore_errors=True)
    try:
        style_json = json.loads((package / "style.json").read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstallError(f"style.json is not valid JSON ({exc})") from exc
    sid = style_json.get("id") if isinstance(style_json, dict) else None
    if not isinstance(sid, str) or not ext.ID_RE.fullmatch(sid):
        raise InstallError("style.json's id must look like ext_<lowercase letters, digits, _>")
    if kind == "gallery" and sid != source.get("id"):
        raise InstallError(f"the gallery entry {source.get('id')!r} unpacks to a different style, {sid!r}")
    if kind == "installed" and sid != source.get("id"):
        raise InstallError(f"the installed folder {source.get('id')!r} holds style {sid!r}")
    pack, reason = ext.check_folder(sid, package)
    try:
        fp = jobfiles.source_fingerprint(package)
    except jobfiles.UnsafePath as exc:
        fp, pack, reason = "", None, str(exc)
    current = ext.approvals(ext.STYLES_DIR).get(sid)
    block = style_json.get("external") if isinstance(style_json.get("external"), dict) else {}
    now = _now()
    record = {
        "id": pid, "style_id": sid, "label": str(style_json.get("label") or sid),
        "version": str(block.get("version", "")), "author": str(block.get("author", "")),
        "licence": str(block.get("licence", "")), "homepage": str(block.get("source", "")),
        "renderer": str(style_json.get("renderer", "")),
        "needs_gpu": bool((style_json.get("needs") or {}).get("gpu")) if isinstance(style_json.get("needs"), dict) else False,
        "source": origin, "reviewed": reviewed,
        "created_at": _iso(now), "expires_at": _iso(now + _dt.timedelta(hours=PENDING_HOURS)),
        "fingerprint": fp, "check": {"ok": pack is not None, "reason": reason},
        "scan": style_scan.scan(package),
        "replaces": ({"version": current.get("version", ""), "fingerprint": current.get("fingerprint", "")}
                     if current else None),
        "audit": None,
    }
    _write_record(work, record)
    _owned_like(work, PENDING_DIR)
    _drop_superseded(record)
    return record


def _origin_key(source) -> tuple | None:
    if not isinstance(source, dict):
        return None
    return tuple(sorted((k, str(v)) for k, v in source.items() if k not in ("commit", "sha256")))


def _drop_superseded(record: dict) -> None:
    """A new stage of the same style from the same source replaces the older one:
    the creation skill stages after every edit."""
    for entry in PENDING_DIR.iterdir():
        if not PID_RE.fullmatch(entry.name) or entry.name == record["id"]:
            continue
        with contextlib.suppress(OSError, ValueError):
            old = json.loads((entry / PENDING_FILE).read_text(encoding="utf-8"))
            if isinstance(old, dict) and old.get("style_id") == record["style_id"] and \
                    _origin_key(old.get("source")) == _origin_key(record["source"]):
                shutil.rmtree(entry, ignore_errors=True)


def _copy_tree(src: pathlib.Path, dest: pathlib.Path) -> None:
    total, count = 0, 0
    for top, dirs, files in os.walk(src, followlinks=False):
        count += len(dirs)  # each one is a mkdir, as in a zip
        for name in files:
            p = os.path.join(top, name)
            if os.path.islink(p):
                raise InstallError(f"{os.path.relpath(p, src)} is a symlink; a style package holds plain files only")
            total += os.path.getsize(p)
            count += 1
    if count > MAX_FILES or total > MAX_UNPACKED_BYTES:
        raise InstallError(f"the folder is over {MAX_FILES} files and folders or {MAX_UNPACKED_BYTES // 1_000_000} MB")
    shutil.copytree(src, dest, symlinks=True)


def _write_record(work: pathlib.Path, record: dict) -> None:
    tmp = work / f"{PENDING_FILE}.tmp"
    tmp.write_text(json.dumps(record, indent=1), encoding="utf-8")
    os.replace(tmp, work / PENDING_FILE)


def get(pid: str) -> dict:
    sweep()
    try:
        return json.loads((_pending_dir(pid) / PENDING_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise InstallError("no such pending install (it may have expired)") from exc


def list_pending() -> list[dict]:
    sweep()
    out = []
    if PENDING_DIR.is_dir():
        for entry in sorted(PENDING_DIR.iterdir()):
            if PID_RE.fullmatch(entry.name):
                with contextlib.suppress(OSError, ValueError):
                    out.append(json.loads((entry / PENDING_FILE).read_text(encoding="utf-8")))
    return sorted(out, key=lambda r: r.get("created_at", ""), reverse=True)


def read_file(pid: str, path: str) -> str:
    """One text file of a staged package, for the install screen."""
    get(pid)
    package = _pending_dir(pid) / "package"
    rel = pathlib.PurePosixPath(path or "")
    if rel.is_absolute() or ".." in rel.parts or not rel.parts:
        raise InstallError("no such file in the package")
    target = package.joinpath(*rel.parts)
    if target.is_symlink() or not target.is_file() or rel.suffix.lower() not in style_scan._TEXT_SUFFIXES | {""}:
        raise InstallError("no such text file in the package")
    if target.stat().st_size > 1_000_000:
        raise InstallError("the file is too large to show here")
    return target.read_text(encoding="utf-8", errors="replace")


def set_audit(pid: str, verdict: str, notes: str) -> dict:
    if verdict not in ("no_concerns", "concerns", "refuse"):
        raise InstallError("verdict must be no_concerns, concerns or refuse")
    with _lock():
        record = get(pid)
        record["audit"] = {"verdict": verdict, "notes": str(notes or "")[:20_000], "at": _iso(_now())}
        _write_record(_pending_dir(pid), record)
    return record


def discard(pid: str) -> None:
    with _lock():
        get(pid)
        shutil.rmtree(_pending_dir(pid), ignore_errors=True)


def confirm(pid: str) -> dict:
    """Install a staged package. The caller has checked that a person is saying yes."""
    with _lock():
        record = get(pid)
        work = _pending_dir(pid)
        package = work / "package"
        sid = record["style_id"]
        if not record["check"]["ok"]:
            raise InstallError(f"the package cannot be installed: {record['check']['reason']}")
        if record["scan"]["refusals"]:
            raise InstallError("the scan refused the package: " + "; ".join(record["scan"]["refusals"][:3]))
        styles = ext.STYLES_DIR
        dest = styles / sid
        incoming = styles / f".incoming-{pid}"
        old = styles / f".replaced-{pid}"
        shutil.rmtree(incoming, ignore_errors=True)
        # copy first, then fingerprint the copy: the staged folder sits on a
        # mount other processes can write, and what is checked is what installs
        shutil.copytree(package, incoming, symlinks=True)
        try:
            fp = jobfiles.source_fingerprint(incoming)
        except jobfiles.UnsafePath as exc:
            shutil.rmtree(incoming, ignore_errors=True)
            raise InstallError(str(exc)) from exc
        if fp != record["fingerprint"]:
            shutil.rmtree(incoming, ignore_errors=True)
            raise InstallError("the staged package changed after it was scanned; stage it again")
        _owned_like(incoming, styles)
        if dest.is_symlink():
            dest.unlink()
        elif dest.exists():
            os.replace(dest, old)
        os.replace(incoming, dest)
        shutil.rmtree(old, ignore_errors=True)
        source = dict(record["source"])
        # the fingerprint checked above, never one taken now: a file edited since
        # leaves the package waiting for review instead of approving the edit
        ext.approve(styles, sid, fingerprint=fp, version=record["version"], source=source,
                    reviewed=record["reviewed"], installed_at=_iso(_now()), label=record["label"])
        with contextlib.suppress(OSError):
            os.chmod(styles / ext.INSTALLED, 0o644)
        _owned_like(styles / ext.INSTALLED, styles)
        shutil.rmtree(work, ignore_errors=True)
    return {"style_id": sid, "version": record["version"], "fingerprint": fp}


def remove(sid: str) -> None:
    """Delete an installed package and its approval. The caller has checked
    that no video or domain uses it."""
    if not ext.ID_RE.fullmatch(sid or ""):
        raise InstallError("no such external style")
    with _lock():
        styles = ext.STYLES_DIR
        dest = styles / sid
        if not (dest.exists() or dest.is_symlink()) and sid not in ext.approvals(styles):
            raise InstallError(f"{sid} is not installed")
        gone = styles / f".removing-{sid}-{secrets.token_hex(4)}"
        if dest.is_symlink():
            dest.unlink()
        elif dest.exists():
            os.replace(dest, gone)
        ext.drop_approval(styles, sid)
        shutil.rmtree(gone, ignore_errors=True)


def make_zip(d: pathlib.Path) -> bytes:
    """A package folder as zip bytes (tests and the creation skill's share step)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, path in sorted(ext._files(pathlib.Path(d)).items()):
            zf.write(path, name)
    return buf.getvalue()
