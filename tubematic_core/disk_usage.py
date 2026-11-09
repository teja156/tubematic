"""How much disk Tubematic uses, and which of its Docker images are old (TMDEV-192).

Two halves, because no container can talk to Docker (no container mounts the
Docker socket, on purpose):

* The data folders under ~/.tubematic-data are all mounted into tubematic-api,
  so the API measures them itself, live, with `tree_bytes`.
* Images, the containers' own writable layers and the install directory are
  only visible from the host. poll.py (hourly), upgrade.py and onboarding
  measure them with `measure_host` and write the result to a small JSON
  snapshot in the data folder (`snapshot_path`), which the API reads.

`old_images` is the one rule for "old image". The dashboard's "old images"
line and upgrade.py's clean-up both use it, so the popup's promise that the
next upgrade removes them stays true.

Docker is only ever read here. Removing an image is upgrade.py's job, through
its Executor, so --dry-run stays honest.
"""
import json
import os
import re
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

SNAPSHOT_NAME = "disk-usage.json"

# Compose's project name (docker-compose.yml pins `name: tubematic`). Compose
# stamps it on every container it creates and every image it builds
# (`com.docker.compose.project`). The e2e stack runs as `tubematic-test`, so
# its images and containers never match.
COMPOSE_PROJECT = "tubematic"
_PROJECT_LABEL = f"label=com.docker.compose.project={COMPOSE_PROJECT}"

# The repositories Tubematic's own images live under. A release install runs
# ghcr.io/<owner>/tubematic-{backend,dashboard}:<version>; the owner is matched
# loosely because a fork publishes under its own owner (release.yml --owner).
# A source install builds tubematic-renderer-image and Compose's default tag
# for the dashboard. Nothing else is ever a candidate: the Kasm workspace
# image (tubematic-kasm-workspace) and the testing images don't match.
_OUR_REPOSITORY = re.compile(
    r"^(ghcr\.io/[^/]+/tubematic-(backend|dashboard)"
    r"|tubematic-renderer-image|tubematic-tubematic-dashboard)$")

DOCKER_TIMEOUT_SECS = 60

# Docker prints sizes through go-units' HumanSize: decimal units.
_SIZE_RE = re.compile(r"^\s*([0-9]+(?:\.[0-9]+)?)\s*([kKMGTP]?)B\s*$")
_SIZE_UNITS = {"": 1, "k": 10**3, "K": 10**3, "M": 10**6, "G": 10**9,
               "T": 10**12, "P": 10**15}


def human(n) -> str:
    """Bytes as `du -h` and the dashboard show them: binary units."""
    n = float(n or 0)
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def snapshot_path(data_root) -> Path:
    """Where the host snapshot lives: the data root's data/ folder, which the
    API container mounts at /data."""
    return Path(data_root) / "data" / SNAPSHOT_NAME


def tree_bytes(path, exclude=()) -> int:
    """Disk used under `path`, the way `du` counts it: allocated blocks, each
    hardlinked file once, symlinks never followed. Anything that cannot be
    read counts as 0 — this feeds a disk-usage figure, never an error.
    `exclude` names paths to leave out (with everything below them)."""
    skip = {os.path.abspath(p) for p in exclude}
    seen = set()
    total = 0
    stack = [os.path.abspath(path)]
    while stack:
        current = stack.pop()
        if current in skip:
            continue
        try:
            st = os.lstat(current)
        except OSError:
            continue
        key = (st.st_dev, st.st_ino)
        if key in seen:
            continue
        seen.add(key)
        total += st.st_blocks * 512
        if not stat.S_ISDIR(st.st_mode):
            continue
        try:
            with os.scandir(current) as entries:
                stack.extend(entry.path for entry in entries)
        except OSError:
            continue
    return total


def parse_size(text) -> int | None:
    """'6.1GB' -> 6100000000. None for anything Docker didn't print as a
    size ('N/A', blank)."""
    m = _SIZE_RE.match(text or "")
    if not m:
        return None
    return int(round(float(m.group(1)) * _SIZE_UNITS[m.group(2)]))


def _default_run(argv):
    return subprocess.run(argv, capture_output=True, text=True,
                          timeout=DOCKER_TIMEOUT_SECS)


def _docker(run, *args) -> str | None:
    """stdout of a read-only docker command, or None when Docker is missing,
    slow or refuses."""
    try:
        r = run(["docker", *args])
    except (OSError, subprocess.SubprocessError):
        return None
    if r.returncode != 0:
        return None
    return r.stdout or ""


def _json_lines(text):
    rows = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _containers(run) -> list | None:
    """[{"image": <full image id>, "size_rw": bytes}] for every container of
    the tubematic project, running or not. None when Docker can't be read."""
    ids = _docker(run, "ps", "-a", "-q", "--no-trunc", "--filter", _PROJECT_LABEL)
    if ids is None:
        return None
    ids = ids.split()
    if not ids:
        return []
    out = _docker(run, "container", "inspect", "--size", *ids)
    if out is None:
        return None
    try:
        rows = json.loads(out)
    except ValueError:
        return None
    return [{"image": row.get("Image") or "", "size_rw": int(row.get("SizeRw") or 0)}
            for row in rows if isinstance(row, dict)]


def _images(run) -> list | None:
    """Every image on the machine as {"id", "repository", "tag"} — one row per
    tag, like `docker image ls`. None when Docker can't be read."""
    out = _docker(run, "image", "ls", "--no-trunc", "--format", "{{json .}}")
    if out is None:
        return None
    return [{"id": row.get("ID") or "", "repository": row.get("Repository") or "",
             "tag": row.get("Tag") or ""} for row in _json_lines(out)]


def _dangling_ours(run) -> set:
    out = _docker(run, "image", "ls", "-q", "--no-trunc",
                  "--filter", "dangling=true", "--filter", _PROJECT_LABEL)
    return set((out or "").split())


def _image_sizes(run) -> dict:
    """{image id: {"size": bytes, "unique": bytes}} from `docker system df -v`.
    `unique` is what removing the image would free: layers it shares with
    another image stay. Empty when Docker can't be read."""
    out = _docker(run, "system", "df", "-v", "--format", "{{json .}}")
    try:
        doc = json.loads(out or "")
    except ValueError:
        return {}
    sizes = {}
    for row in (doc.get("Images") or []) if isinstance(doc, dict) else []:
        if not isinstance(row, dict):
            continue
        size = parse_size(row.get("Size"))
        unique = parse_size(row.get("UniqueSize"))
        sizes[row.get("ID") or ""] = {"size": size or 0,
                                      "unique": unique if unique is not None else (size or 0)}
    return sizes


def _build_cache_bytes(run) -> int | None:
    out = _docker(run, "system", "df", "--format", "{{json .}}")
    if out is None:
        return None
    for row in _json_lines(out):
        if str(row.get("Type", "")).lower().replace(" ", "") == "buildcache":
            return parse_size(row.get("Size"))
    return None


def old_images(run=_default_run) -> list:
    """Tubematic's images that no Tubematic container uses, as
    [{"id": <full id>, "refs": ["repo:tag", ...], "bytes": <what removing it
    frees>}]. An entry with no refs is untagged and is removed by id; a tagged
    one by its refs, which avoids Docker's "referenced in multiple
    repositories" refusal.

    A candidate is an image under one of Tubematic's repositories (any tag,
    including a `<none>` left by a re-pushed tag) or an untagged image Compose
    built for this project. Every image any tubematic container uses — running
    or stopped — is excluded.

    No tubematic containers at all means nothing can be told apart from what
    is in use (the stack is down or gone), so nothing is old: this never names
    an image when it cannot see what the install runs."""
    containers = _containers(run)
    if not containers:
        return []
    return _old_images(run, containers, _image_sizes(run))


def _old_images(run, containers, sizes) -> list:
    if not containers:
        return []
    in_use = {c["image"] for c in containers}
    images = _images(run)
    if images is None:
        return []
    found = {}
    for row in images:
        if row["id"] in in_use or not _OUR_REPOSITORY.match(row["repository"]):
            continue
        entry = found.setdefault(row["id"], _old_entry(row["id"], sizes))
        if row["tag"] and row["tag"] != "<none>":
            entry["refs"].append(f"{row['repository']}:{row['tag']}")
    for image_id in _dangling_ours(run):
        if image_id not in in_use:
            found.setdefault(image_id, _old_entry(image_id, sizes))
    return sorted(found.values(), key=lambda e: e["id"])


def _old_entry(image_id, sizes) -> dict:
    return {"id": image_id, "refs": [], "bytes": sizes.get(image_id, {}).get("unique", 0)}


def measure_host(install_dir, run=_default_run) -> dict:
    """The host-only half of the figures. A field is None when Docker could
    not be read, so the dashboard says "unknown" rather than "0 B"."""
    snapshot = {"images": None, "containers_bytes": None, "build_cache_bytes": None,
                "install_bytes": tree_bytes(install_dir)}
    containers = _containers(run)
    if containers is None:
        return snapshot
    sizes = _image_sizes(run)
    snapshot["containers_bytes"] = sum(c["size_rw"] for c in containers)
    current = {c["image"] for c in containers}
    old = _old_images(run, containers, sizes)
    snapshot["images"] = {
        "current_bytes": sum(sizes.get(i, {}).get("size", 0) for i in current),
        "old_bytes": sum(e["bytes"] for e in old),
        "old_count": len(old),
    }
    snapshot["build_cache_bytes"] = _build_cache_bytes(run)
    return snapshot


def write_snapshot(path, data: dict) -> None:
    """Write atomically: a reader sees the old file or the new one, never half."""
    path = Path(path)
    body = dict(data)
    body["measured_at"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(body))
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def read_snapshot(path) -> dict | None:
    """The host snapshot, or None when it is missing or unreadable."""
    try:
        doc = json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None
    if not isinstance(doc, dict) or not isinstance(doc.get("measured_at"), str):
        return None
    return doc


def refresh_snapshot(data_root, install_dir, *, max_age=None, run=_default_run) -> bool:
    """Measure the host and write the snapshot. With `max_age` (seconds),
    leave a snapshot younger than that alone. Returns True when it wrote.
    A failure to write (an unwritable data folder) raises OSError for the
    caller to report; Docker being unavailable never raises."""
    path = snapshot_path(data_root)
    if max_age is not None:
        try:
            age = datetime.now().timestamp() - path.stat().st_mtime
        except OSError:
            age = None
        if age is not None and 0 <= age < max_age:
            return False
    write_snapshot(path, measure_host(install_dir, run=run))
    return True
