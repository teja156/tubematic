"""MCP's side of the code sandbox (TMDEV-242): hand code to the
`tubematic-sandbox` container through the shared spool folder and read the
outcome back.

This file never runs code. There is no fallback: when the sandbox is not
answering, the caller gets `sandbox_unavailable`, because running agent code in
this container is what `write_gif_script` did and why it was deleted
(tests/test_removed_tools.py). The protocol is
tubematic_core/sandbox_protocol.py; the daemon is sandbox/daemon.py.

What the agent may feed a run is a short allowlist of one video's own files,
copied into the spool (the sandbox mounts nothing else). What comes back is
re-checked here, because the daemon's output is the output of untrusted code:
names, sizes, counts, and that a picture is a picture, before anything lands in
`<job>/runs/<run_id>/`.

I/O only: no database, no tool registration (server.py::run_code does that).
"""
from __future__ import annotations

import json
import os
import secrets
import shutil
import stat
import time
from pathlib import Path

from tubematic_core import jobfiles as tjobs
from tubematic_core import sandbox_protocol as P

POLL_S = 0.1
# Run directories kept per video; the oldest are removed past this.
MAX_RUNS_KEPT = 20
RESULT_GRACE_S = 10
PER_QUEUED_S = 25

_MAGIC = {".png": (b"\x89PNG\r\n\x1a\n",), ".jpg": (b"\xff\xd8\xff",), ".jpeg": (b"\xff\xd8\xff",),
          ".webp": (b"RIFF",)}


class SandboxError(Exception):
    """A refusal the tool returns as {"error": code, "detail": ...}."""

    def __init__(self, code: str, detail: str):
        super().__init__(detail)
        self.code, self.detail = code, detail

    def as_dict(self) -> dict:
        return {"error": self.code, "detail": self.detail}


def spool_dir() -> Path | None:
    value = os.environ.get("TUBEMATIC_SANDBOX_DIR", "").strip()
    return Path(value) if value else None


def check_available(spool) -> None:
    """Raise SandboxError unless the daemon has beaten recently and the queue has room."""
    if spool is None:
        raise SandboxError("sandbox_unavailable", "this install has no code sandbox configured")
    age = P.heartbeat_age(spool)
    if age is None or age > P.HEARTBEAT_MAX_AGE_S:
        raise SandboxError("sandbox_unavailable",
                           "the tubematic-sandbox container is not answering; code cannot be run right now. "
                           "Carry on without running it (never retry in a loop)")
    if queue_length(spool) >= P.MAX_QUEUED:
        raise SandboxError("sandbox_busy", "other runs are waiting; try again in a minute")


def queue_length(spool) -> int:
    try:
        return sum(1 for n in os.listdir(Path(spool) / "req") if P.REQUEST_ID_RE.match(n))
    except OSError:
        return 0


# --- inputs -----------------------------------------------------------------

def resolve_inputs(jobs_dir, video_id: str, names) -> list[tuple[str, Path]]:
    """Map job-relative names to (alias, path). Allowed: timeline.json,
    scene-config.json, images/<file>, images/treated/<file>, runs/<id>/<file>.
    The alias (the file's base name) is what the code sees in ./in/."""
    if names is None:
        names = []
    if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
        raise SandboxError("bad_inputs", "inputs must be a list of job-relative file names")
    if len(names) > P.MAX_INPUT_FILES:
        raise SandboxError("bad_inputs", f"at most {P.MAX_INPUT_FILES} input files")
    out, total, seen = [], 0, set()
    for name in names:
        parts = name.split("/")
        try:
            if name in (tjobs.TIMELINE, tjobs.SCENE_CONFIG):
                path = tjobs.job_file(jobs_dir, video_id, name)
            elif len(parts) == 2 and parts[0] == tjobs.IMAGES:
                path = tjobs.image_file(jobs_dir, video_id, parts[1])
            elif len(parts) == 3 and parts[:2] == [tjobs.IMAGES, tjobs.TREATED]:
                path = tjobs.join_below(jobs_dir, video_id, tjobs.IMAGES, tjobs.TREATED, _component(parts[2]))
            elif len(parts) == 3 and parts[0] == tjobs.RUNS:
                path = tjobs.run_file(jobs_dir, video_id, parts[1], parts[2])
            else:
                raise SandboxError("bad_inputs", f"{name!r} is not a file a run may read (timeline.json, "
                                   "scene-config.json, images/<file>, images/treated/<file>, runs/<run>/<file>)")
        except tjobs.UnsafePath as e:
            raise SandboxError("bad_inputs", str(e))
        alias = parts[-1]
        if not P.name_ok(alias):
            raise SandboxError("bad_inputs", f"{alias!r}: file names for a run use letters, digits, . _ -")
        if alias in seen:
            raise SandboxError("bad_inputs", f"two inputs are both called {alias!r}")
        seen.add(alias)
        try:
            st = os.lstat(path)
        except OSError:
            raise SandboxError("bad_inputs", f"{name!r} does not exist for this video")
        if not stat.S_ISREG(st.st_mode):
            raise SandboxError("bad_inputs", f"{name!r} is not a regular file")
        if st.st_size > P.MAX_INPUT_FILE_BYTES:
            raise SandboxError("bad_inputs", f"{name!r} is larger than {P.MAX_INPUT_FILE_BYTES // 2**20} MB")
        total += st.st_size
        if total > P.MAX_INPUT_TOTAL_BYTES:
            raise SandboxError("bad_inputs", "the inputs add up to more than "
                               f"{P.MAX_INPUT_TOTAL_BYTES // 2**20} MB")
        out.append((alias, path))
    return out


def _component(part: str) -> str:
    from tubematic_core import ids
    if not ids.is_component(part):
        raise tjobs.UnsafePath(f"{part!r} cannot be used as a file name")
    return part


# --- a run ------------------------------------------------------------------

def submit(spool, language: str, code: str, timeout_s: float, inputs: list[tuple[str, Path]]) -> str:
    """Write one request; returns its id. Never raises for a full queue (check_available does)."""
    spool = Path(spool)
    rid = secrets.token_hex(8)
    tmp = spool / "req" / f".{rid}.tmp"
    try:
        (tmp / "in").mkdir(parents=True)
        for alias, src in inputs:
            shutil.copyfile(src, tmp / "in" / alias)
        (tmp / "request.json").write_text(json.dumps({
            "language": language, "code": code, "timeout_s": timeout_s, "inputs": [a for a, _ in inputs]}),
            encoding="utf-8")
        tmp.rename(spool / "req" / rid)
    except OSError as e:
        shutil.rmtree(tmp, ignore_errors=True)
        raise SandboxError("sandbox_unavailable", f"could not hand the code to the sandbox: {e}")
    return rid


def wait_for_result(spool, rid: str, timeout_s: float, queued_ahead: int = 0, sleep=time.sleep,
                    clock=time.monotonic) -> dict:
    """The run's result.json, or SandboxError when it never arrives."""
    spool = Path(spool)
    deadline = clock() + timeout_s + RESULT_GRACE_S + PER_QUEUED_S * queued_ahead
    final = spool / "done" / rid
    while clock() < deadline:
        if (final / "result.json").is_file():
            try:
                return json.loads((final / "result.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raise SandboxError("sandbox_error", "the sandbox returned an unreadable result")
        sleep(POLL_S)
    shutil.rmtree(spool / "req" / rid, ignore_errors=True)
    raise SandboxError("sandbox_timeout", "the sandbox did not finish in time; the run was dropped")


def clean_result(result: dict) -> dict:
    """The daemon's result reduced to the fields and types the protocol defines."""
    def text(v):
        return v if isinstance(v, str) else ""
    def num(v):
        return v if isinstance(v, int) and not isinstance(v, bool) else None
    return {"exit_code": num(result.get("exit_code")), "signal": num(result.get("signal")),
            "timed_out": result.get("timed_out") is True, "output_truncated": result.get("output_truncated") is True,
            "stdout": P.cut(text(result.get("stdout")))[0], "stderr": P.cut(text(result.get("stderr")))[0],
            "duration_ms": num(result.get("duration_ms")) or 0,
            "error": result.get("error") if isinstance(result.get("error"), str) else None}


def _looks_right(path: Path, ext: str) -> bool:
    """A picture starts like its extension says; text files decode as UTF-8."""
    with open(path, "rb") as f:
        head = f.read(16)
    if ext in _MAGIC:
        if not any(head.startswith(m) for m in _MAGIC[ext]):
            return False
        return ext != ".webp" or head[8:12] == b"WEBP"
    try:
        path.read_bytes().decode("utf-8")
    except UnicodeDecodeError:
        return False
    return True


def store_outputs(spool, rid: str, jobs_dir, video_id: str) -> list[dict]:
    """Move the run's files from the spool into <job>/runs/<rid>/, after
    checking each one again. Returns [{name, size, path}]. Removes done/<rid>."""
    spool = Path(spool)
    src = spool / "done" / rid / "out"
    kept, total = [], 0
    try:
        names = sorted(os.listdir(src))
    except OSError:
        names = []
    try:
        for name in names:
            if len(kept) >= P.MAX_OUT_FILES:
                break
            path = src / name
            try:
                st = os.lstat(path)
            except OSError:
                continue
            if (not stat.S_ISREG(st.st_mode) or not P.out_name_ok(name) or st.st_size > P.MAX_OUT_FILE_BYTES
                    or total + st.st_size > P.MAX_OUT_TOTAL_BYTES
                    or not _looks_right(path, Path(name).suffix.lower())):
                continue
            dest = tjobs.run_file(jobs_dir, video_id, rid, name)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, dest)
            kept.append({"name": name, "size": st.st_size, "path": f"{tjobs.RUNS}/{rid}/{name}"})
            total += st.st_size
        if kept:
            prune_runs(jobs_dir, video_id)
    finally:
        shutil.rmtree(spool / "done" / rid, ignore_errors=True)
    return kept


def prune_runs(jobs_dir, video_id: str, keep: int = MAX_RUNS_KEPT) -> None:
    """Keep the newest `keep` run folders of a video."""
    try:
        base = tjobs.runs_dir(jobs_dir, video_id)
        runs = sorted((p for p in base.iterdir() if p.is_dir() and not p.is_symlink()),
                      key=lambda p: p.stat().st_mtime)
    except (OSError, tjobs.UnsafePath):
        return
    for old in runs[:-keep] if len(runs) > keep else []:
        shutil.rmtree(old, ignore_errors=True)


def run(spool, jobs_dir, video_id: str, language: str, code: str, timeout_s: float, input_names) -> dict:
    """One whole run: check, copy in, wait, store out. Raises SandboxError."""
    if language not in P.LANGUAGES:
        raise SandboxError("bad_language", f"language must be one of {', '.join(P.LANGUAGES)}")
    if not isinstance(code, str) or not code.strip():
        raise SandboxError("bad_code", "no code given")
    if len(code.encode("utf-8")) > P.MAX_CODE_BYTES:
        raise SandboxError("bad_code", f"code is larger than {P.MAX_CODE_BYTES // 1024} KB")
    if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)) or not 0 < timeout_s <= P.MAX_TIMEOUT_S:
        raise SandboxError("bad_timeout", f"timeout_s must be between 0 and {P.MAX_TIMEOUT_S}")
    inputs = resolve_inputs(jobs_dir, video_id, input_names)
    check_available(spool)
    ahead = queue_length(spool)
    rid = submit(spool, language, code, timeout_s, inputs)
    result = wait_for_result(spool, rid, timeout_s, ahead)
    out = clean_result(result)
    if out["error"]:
        shutil.rmtree(Path(spool) / "done" / rid, ignore_errors=True)
        raise SandboxError("sandbox_error", out["error"])
    out["files"] = store_outputs(spool, rid, jobs_dir, video_id)
    out["run_id"] = rid
    return out
