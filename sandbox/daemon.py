"""The code sandbox's daemon (TMDEV-242): runs the code the agent hands MCP.

Runs as PID 1 of the `tubematic-sandbox` container: no network, a read-only
root, one mount (the spool folder it shares with tubematic-mcp), no secrets.
It takes a request from <spool>/req, runs the code as an unprivileged child
(uid 65534) in a fresh work folder on the container's tmpfs, and writes the
outcome to <spool>/done. The protocol is tubematic_core/sandbox_protocol.py.

The container is the boundary; this file adds the second line of defence
inside it: the code runs as another uid than the daemon, with no capabilities
and a scrubbed environment, under CPU, file-size, process and (Python)
address-space limits and a wall-clock kill of its whole process group, and
only regular files with allowed names it leaves in ./out are handed back.

Stdlib only. One run at a time. A run that goes wrong must never stop the
loop: every exception on a request becomes that request's error result.
"""
from __future__ import annotations

import json
import os
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import traceback
from dataclasses import dataclass
from pathlib import Path

from tubematic_core import sandbox_protocol as P

NOBODY = 65534
POLL_S = 0.2
RUN_ENV = {"PATH": "/usr/local/bin:/usr/bin:/bin", "LANG": "C.UTF-8", "PYTHONDONTWRITEBYTECODE": "1",
           "PYTHONIOENCODING": "utf-8", "NODE_OPTIONS": "--max-old-space-size=384"}
LIMITS_NPROC = 128
LIMITS_NOFILE = 256
LIMITS_AS_PYTHON = 1536 * 1024 * 1024


@dataclass
class Config:
    spool: Path
    work_root: Path = Path("/tmp")
    # (uid, gid) the code runs as; None only in tests that are not root.
    run_as: tuple[int, int] | None = (NOBODY, NOBODY)
    esbuild: str = "/app/remotion/node_modules/.bin/esbuild"
    # Counts every process of the uid, so it is only meaningful when the code
    # runs as a uid of its own (the container); tests as a normal user turn it off.
    nproc: int | None = LIMITS_NPROC
    # Other world-writable folders the code could leave something in: Docker mounts /dev/shm
    # writable even under a read-only root.
    wipe_also: tuple[Path, ...] = (Path("/dev/shm"),)
    python: str = "python3"
    node: str = "node"


def _log(msg: str) -> None:
    print(f"[sandbox] {msg}", file=sys.stderr, flush=True)


def _kill_group(pgid: int) -> None:
    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        pass


def kill_leftovers(uid: int) -> int:
    """SIGKILL every process owned by `uid` (a child that left its process
    group). Returns how many it signalled. Scans /proc; never signals the
    daemon itself."""
    me, n = os.getpid(), 0
    for entry in os.listdir("/proc"):
        if not entry.isdigit() or int(entry) == me:
            continue
        try:
            if os.stat(f"/proc/{entry}").st_uid == uid:
                os.kill(int(entry), signal.SIGKILL)
                n += 1
        except (OSError, ProcessLookupError):
            continue
    return n


def reap_zombies() -> int:
    """Collect every exited orphan. The daemon is PID 1 of its container, so a
    process the code started and left behind (a fork bomb's children, killed
    with the run) is re-parented to it and stays a zombie until someone waits
    for it; enough of them would fill the container's process limit."""
    n = 0
    while True:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return n
        if pid == 0:
            return n
        n += 1


def wipe_owned(root: Path, uid: int) -> int:
    """Delete everything directly under `root` that `uid` owns: what a run left
    on the shared tmpfs outside its own work folder, so the next run cannot find
    it. Returns how many entries it removed."""
    n = 0
    for entry in os.scandir(root):
        try:
            if entry.stat(follow_symlinks=False).st_uid != uid:
                continue
            if entry.is_dir(follow_symlinks=False):
                shutil.rmtree(entry.path, ignore_errors=True)
            else:
                os.unlink(entry.path)
            n += 1
        except OSError:
            continue
    return n


def _limiter(cpu_seconds: int, language: str, nproc: int | None):
    def apply():
        os.setsid()
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        resource.setrlimit(resource.RLIMIT_FSIZE, (P.MAX_WRITE_BYTES, P.MAX_WRITE_BYTES))
        if nproc is not None:
            resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))
        resource.setrlimit(resource.RLIMIT_NOFILE, (LIMITS_NOFILE, LIMITS_NOFILE))
        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        if language == "python":
            # V8 reserves address space it never uses, so Node is held by its
            # own heap flag and the container's memory limit instead.
            resource.setrlimit(resource.RLIMIT_AS, (LIMITS_AS_PYTHON, LIMITS_AS_PYTHON))
    return apply


def _run(cfg: Config, argv: list[str], work: Path, runner: Path, timeout: float, language: str,
         beat) -> dict:
    """One child process. Returns exit_code/signal/timed_out and its two streams."""
    out_f = open(runner / "stdout", "wb")
    err_f = open(runner / "stderr", "wb")
    env = dict(RUN_ENV, HOME=str(work), TMPDIR=str(work))
    kwargs = {}
    if cfg.run_as is not None:
        kwargs = {"user": cfg.run_as[0], "group": cfg.run_as[1], "extra_groups": []}
    started = time.monotonic()
    timed_out = False
    try:
        proc = subprocess.Popen(argv, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=out_f,
                                stderr=err_f, close_fds=True,
                                preexec_fn=_limiter(int(timeout) + 2, language, cfg.nproc), **kwargs)
        while True:
            try:
                proc.wait(timeout=0.25)
                break
            except subprocess.TimeoutExpired:
                beat()
                if time.monotonic() - started > timeout:
                    timed_out = True
                    _kill_group(proc.pid)
                    proc.wait()
                    break
    finally:
        out_f.close()
        err_f.close()
    _kill_group(proc.pid)
    if cfg.run_as is not None:
        kill_leftovers(cfg.run_as[0])
        time.sleep(0.2)
    reap_zombies()
    code = proc.returncode
    sig = -code if code < 0 else None
    streams = {}
    truncated = False
    for name in ("stdout", "stderr"):
        raw = (runner / name).read_bytes()[: P.MAX_WRITE_BYTES]
        text, cut = P.cut(raw.decode("utf-8", errors="replace"))
        streams[name] = text
        truncated = truncated or cut or len(raw) >= P.MAX_WRITE_BYTES
    return {"exit_code": None if sig else code, "signal": sig, "timed_out": timed_out,
            "output_truncated": truncated, "stdout": streams["stdout"], "stderr": streams["stderr"],
            "duration_ms": int((time.monotonic() - started) * 1000)}


def _chown(path: Path, cfg: Config) -> None:
    if cfg.run_as is not None:
        os.chown(path, cfg.run_as[0], cfg.run_as[1])


def _stage(cfg: Config, req: dict, req_dir: Path, work: Path) -> None:
    """Make the work folder: in/ (copies of the inputs), out/, and the source."""
    (work / "in").mkdir()
    (work / "out").mkdir()
    for alias in req.get("inputs") or []:
        src = req_dir / "in" / alias
        if P.name_ok(alias) and src.is_file() and not src.is_symlink():
            shutil.copyfile(src, work / "in" / alias)
    (work / P.SOURCE_NAME[req["language"]]).write_text(req["code"], encoding="utf-8")
    for p in [work, *work.rglob("*")]:
        _chown(p, cfg)
    # mkdtemp made `work` 0700; without CAP_FOWNER root could not chmod it after the chown.


def _validate(req) -> str | None:
    if not isinstance(req, dict):
        return "request is not an object"
    if req.get("language") not in P.LANGUAGES:
        return f"unsupported language {req.get('language')!r}"
    code = req.get("code")
    if not isinstance(code, str) or not code.strip():
        return "no code"
    if len(code.encode("utf-8")) > P.MAX_CODE_BYTES:
        return "code is too large"
    timeout = req.get("timeout_s")
    if not isinstance(timeout, (int, float)) or isinstance(timeout, bool) or not 0 < timeout <= P.MAX_TIMEOUT_S:
        return "bad timeout"
    inputs = req.get("inputs", [])
    if not isinstance(inputs, list) or len(inputs) > P.MAX_INPUT_FILES or not all(P.name_ok(i) for i in inputs):
        return "bad inputs"
    return None


def collect_outputs(work_out: Path, dest: Path) -> list[dict]:
    """Copy the files the code left in ./out into `dest`, keeping only regular
    files (never a symlink, a directory or a device) with an allowed name and
    extension, within the count and size limits. Called after the child is
    dead, so nothing can change under it."""
    kept, total = [], 0
    dest.mkdir()
    for entry in sorted(os.listdir(work_out)):
        if len(kept) >= P.MAX_OUT_FILES:
            break
        path = work_out / entry
        try:
            st = os.lstat(path)
        except OSError:
            continue
        if not (os.path.isfile(path) and not os.path.islink(path)) or not P.out_name_ok(entry):
            continue
        if st.st_size > P.MAX_OUT_FILE_BYTES or total + st.st_size > P.MAX_OUT_TOTAL_BYTES:
            continue
        fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW)
        try:
            with os.fdopen(fd, "rb") as src, open(dest / entry, "wb") as dst:
                shutil.copyfileobj(src, dst)
        except OSError:
            continue
        kept.append({"name": entry, "size": st.st_size})
        total += st.st_size
    return kept


def execute(cfg: Config, req: dict, req_dir: Path, done_tmp: Path, beat=lambda: None) -> dict:
    """Run one validated request. Writes done_tmp/out/*; returns the result."""
    work = Path(tempfile.mkdtemp(prefix="work-", dir=cfg.work_root))
    runner = Path(tempfile.mkdtemp(prefix="runner-", dir=cfg.work_root))
    try:
        _stage(cfg, req, req_dir, work)
        language, timeout = req["language"], float(req["timeout_s"])
        steps = []
        if language == "python":
            steps.append(([cfg.python, "-I", "main.py"], "python"))
        else:
            if language == "typescript":
                steps.append(([cfg.esbuild, "main.ts", "--outfile=main.js", "--format=cjs", "--log-level=error"],
                              "node"))
            steps.append(([cfg.node, "main.js"], "node"))
        result = None
        started = time.monotonic()
        for argv, lang in steps:
            # One budget for the whole request: transpiling and running share timeout_s.
            left = timeout - (time.monotonic() - started)
            if result is not None and left <= 0:
                # The transpile used the whole budget: the program never ran, which is a timeout, not a success.
                result.update(timed_out=True, exit_code=None, stderr=(result["stderr"] + "\ntime ran out before the program started").strip())
                break
            result = _run(cfg, argv, work, runner, max(left, 0.5), lang, beat)
            if result["exit_code"] != 0:
                break
        files = collect_outputs(work / "out", done_tmp / "out")
        result["files"] = files
        result["error"] = None
        return result
    finally:
        shutil.rmtree(work, ignore_errors=True)
        shutil.rmtree(runner, ignore_errors=True)
        if cfg.run_as is not None:
            for root in (cfg.work_root, *cfg.wipe_also):
                if root.is_dir():
                    wipe_owned(root, cfg.run_as[0])


def _error_result(rid: str, message: str) -> dict:
    return {"id": rid, "exit_code": None, "signal": None, "timed_out": False, "output_truncated": False,
            "stdout": "", "stderr": "", "duration_ms": 0, "files": [], "error": message}


def process_request(cfg: Config, req_dir: Path, beat=lambda: None) -> None:
    rid = req_dir.name
    done = cfg.spool / "done"
    tmp = done / f".{rid}.tmp"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    try:
        try:
            req = json.loads((req_dir / "request.json").read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            result = _error_result(rid, f"unreadable request: {e}")
        else:
            problem = _validate(req)
            result = _error_result(rid, problem) if problem else execute(cfg, req, req_dir, tmp, beat)
    except Exception as e:  # a bad run must never stop the loop
        _log(f"request {rid} failed: {e!r}\n{traceback.format_exc()}")
        shutil.rmtree(tmp / "out", ignore_errors=True)
        result = _error_result(rid, f"sandbox error: {type(e).__name__}")
    result["id"] = rid
    (tmp / "result.json").write_text(json.dumps(result), encoding="utf-8")
    final = done / rid
    shutil.rmtree(final, ignore_errors=True)
    tmp.rename(final)
    shutil.rmtree(req_dir, ignore_errors=True)


def pending(cfg: Config) -> list[Path]:
    req = cfg.spool / "req"
    try:
        names = sorted(n for n in os.listdir(req) if P.REQUEST_ID_RE.match(n))
    except OSError:
        return []
    found = []
    for n in names:
        try:
            found.append(((req / n).stat().st_mtime, req / n))
        except OSError:
            continue  # MCP dropped a request that timed out while we were listing
    return [p for _, p in sorted(found)]


def sweep(cfg: Config, now: float | None = None) -> None:
    """Remove requests nobody ran, results nobody fetched and half-written
    temporaries a crash left, once they are older than STALE_AFTER_S. A
    temporary is not removed sooner: MCP may still be copying into it."""
    now = time.time() if now is None else now
    for sub in ("req", "done"):
        d = cfg.spool / sub
        try:
            names = os.listdir(d)
        except OSError:
            continue
        for n in names:
            p = d / n
            try:
                if now - p.stat().st_mtime > P.STALE_AFTER_S:
                    shutil.rmtree(p, ignore_errors=True)
            except OSError:
                pass


def prepare(cfg: Config) -> None:
    # The code runs as another uid: nobody may write into the spool's top
    # level but its owner (and the heartbeat/req/done are 0700 or root's).
    try:
        os.chmod(cfg.spool, 0o755)
    except OSError:
        pass
    for sub in ("req", "done"):
        d = cfg.spool / sub
        d.mkdir(exist_ok=True)
        os.chmod(d, 0o700)


def serve_once(cfg: Config) -> bool:
    """Run the oldest pending request. Returns whether there was one."""
    todo = pending(cfg)
    if not todo:
        return False
    beat = lambda: P.write_heartbeat(cfg.spool)
    process_request(cfg, todo[0], beat)
    return True


def main() -> None:
    cfg = Config(spool=Path(os.environ.get("SANDBOX_SPOOL", "/spool")))
    prepare(cfg)
    sweep(cfg)
    _log(f"ready, spool {cfg.spool}")
    last_sweep = 0.0
    while True:
        try:
            P.write_heartbeat(cfg.spool)
            if not serve_once(cfg):
                time.sleep(POLL_S)
            reap_zombies()
        except Exception as e:  # nothing a request or the spool does may stop the daemon
            _log(f"loop error: {e!r}\n{traceback.format_exc()}")
            time.sleep(1)
        if time.time() - last_sweep > 60:
            sweep(cfg)
            last_sweep = time.time()


if __name__ == "__main__":
    main()
