#!/usr/bin/env python3
"""Tubematic renderer: renders what the render gateway hands it.

A renderer has no database. Every renderer — the built-in one in the
tubematic-renderer container and any remote host — talks to main's API over
HTTPS through the render gateway (render_gateway.py) and nothing else:

  1. it proves who it is: the built-in renderer with the builtin_renderer_token
     secret (read per request, so a rotation needs no restart), a remote one
     with the credential it was issued at enrollment (its state file), and it
     trusts exactly the gateway's pinned certificate;
  2. it tests its GPU (the probe below) and sends the answer with its first
     heartbeat, which says `started` so the gateway re-queues whatever this
     renderer held before it restarted;
  3. a heartbeat thread reports every HEARTBEAT_SECS what it is doing (which
     keeps the lease on the claim it renders alive), carries any new probe,
     and applies the reply: stop a render the gateway no longer wants (the
     stop names a claim, and is applied only to the job the heartbeat
     reported, never to a newer claim of the same video started since), run
     a probe the dashboard asked for, save a rotated credential;
  4. the loop claims a video, downloads its bundle (the job's files as one tar
     stream) into a job directory of its own, stages it for Remotion, renders
     with the settings the claim carried, uploads the mp4 and reports how the
     render ended. The bundle, the upload and the result name the claim
     (its claim id, the X-Render-Claim header), so a renderer that lost its
     lease cannot touch the claim that took the video over. What a failed render does to its video — a retry, a
     revision, FAILED — is decided by the gateway (render_results.py), and the
     AI review runs in tubematic-worker; the renderer only reports what
     happened, and whether a GPU it rendered on still passes its test.

A network error is never fatal: it is logged, reported as last_error on the
next heartbeat that gets through, and retried later.

Everything else the old single worker loop did (publishing, Auto Pilot,
metrics, price sync, retention, notifications, the stalled-voicing sweep) runs
in tubematic-worker (worker.py), so a render that holds this loop for an hour
never delays a publish, an approval or a notification, and recreating this
container (onboard.py --step gpu does) never interrupts them either.

Run: python3 render_agent.py
"""
import hashlib
import hmac
import json
import re
import shutil
import socket
import ssl
import tarfile
import threading
import logging
import os
import signal
import subprocess
import sys
import time
import urllib.parse
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import httpx

from tubematic_core import auth as tauth
from tubematic_core import jobfiles as tjobs
from tubematic_core import logging as tlog
from tubematic_core import renderers
from tubematic_core.version import version as current_version

REMOTION_DIR = Path("/app/remotion")
JOBS_DIR = os.getenv("TUBEMATIC_JOBS_DIR", "/jobs")   # the volume the stills server serves as /public/
LOG_DIR = Path(os.getenv("TUBEMATIC_LOG_DIR", "/logs"))
CHROMIUM_BIN = os.getenv("CHROMIUM_BIN", "/usr/bin/chromium")

POLL_INTERVAL_SECS = int(os.getenv("RENDER_POLL_INTERVAL_SECS", "20"))
# The render settings (render_timeout_secs, render_stall_timeout_secs, the
# watermark) are live pipeline settings, but the renderer cannot read the
# settings table: each claim carries their values at the moment it was made.

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [renderer] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    stream=sys.stdout,
)
log = logging.getLogger("render_agent")
# httpx logs every request at INFO: a claim every 20 s and a heartbeat every
# 30 s would be thousands of lines a day of noise. Their warnings and errors
# still show; the renderer's own INFO lines (the "enrolled" and "first
# heartbeat" markers the remote host script waits for among them) are kept.
for _noisy in ("httpx", "httpcore"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)


def _now_precise() -> str:
    """UTC with microseconds, the format of pipeline.now_precise (copied, not
    imported: pipeline is the API's module and the renderer has no database).
    A probe's "at" is compared as a string with the dashboard's request stamp,
    and second precision would let a request made in the same second a probe
    started look already answered."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


# ── Render progress (TMDEV-179) ─────────────────────────────────────────────
#
# A timeout here is a crash detector, not a budget. Total elapsed time is a
# poor proxy for "hung": a legitimate long render on a slow machine looks the
# same as a Chromium wedged at frame 3, and the old 40-minute ceiling made the
# wedged one burn 40 minutes, retry, and burn 40 more. Remotion prints a
# monotonic counter per phase to a plain pipe (newline-terminated, no carriage
# returns, verified on captured logs):
#
#   Bundling 6% … Bundling 100%
#   Rendered 0/60 … Rendered 60/60
#   Encoded 17/60 … Encoded 60/60
#
# so the render is alive while (phase, count) strictly increases. The NUMBER
# must advance, not merely a line arrive: real logs repeat "Rendered 8/60", so
# a stalled render that reprints its count would otherwise read as healthy.
_PROGRESS_RE = re.compile(r"\b(Bundling|Rendered|Encoded)\s+(\d+)")
_PHASE_RANK = {"Bundling": 0, "Rendered": 1, "Encoded": 2}


def _progress_of(line: str):
    """(phase rank, count) when `line` carries one of Remotion's progress
    counters, else None."""
    m = _PROGRESS_RE.search(line)
    if not m:
        return None
    return (_PHASE_RANK[m.group(1)], int(m.group(2)))


# Indirections so the loop below can be driven by a test clock.
_clock = time.monotonic
_sleep = time.sleep
# The upload's busy wait has its own clock (the render watcher's is sped up
# in tests).
_monotonic = time.monotonic
_POLL_SECS = 0.5


def _wait_for_render(proc, timeout_secs: int, stall_secs: int) -> tuple[str, str, str]:
    """Drain both of `proc`'s pipes while it runs and watch its progress.

    Returns (stdout, stderr, outcome): outcome "exited" when the process
    ended by itself, "stall" when the progress counter did not advance for
    stall_secs, "timeout" when timeout_secs elapsed in all. On "stall" and
    "timeout" the process is still running: the caller kills its group.

    Both pipes are read on threads of their own: a hand-rolled read of stdout
    alone deadlocks the moment a chatty render fills the stderr pipe, and
    communicate() hands both over only at the end, which is why it could not
    see progress. The full output is kept: a failed render reports it.
    """
    out_lines: list[str] = []
    err_lines: list[str] = []
    state = {"progress": (-1, -1), "advanced_at": _clock()}
    lock = threading.Lock()

    def pump(stream, sink):
        for line in iter(stream.readline, ""):
            sink.append(line)
            p = _progress_of(line)
            if p is None:
                continue
            with lock:
                if p > state["progress"]:
                    state["progress"] = p
                    state["advanced_at"] = _clock()
        stream.close()

    threads = [threading.Thread(target=pump, args=(proc.stdout, out_lines), daemon=True),
               threading.Thread(target=pump, args=(proc.stderr, err_lines), daemon=True)]
    for t in threads:
        t.start()
    started = _clock()
    outcome = "exited"
    while proc.poll() is None:
        now = _clock()
        if now - started > timeout_secs:
            outcome = "timeout"
            break
        with lock:
            quiet = now - state["advanced_at"]
        if quiet > stall_secs:
            outcome = "stall"
            break
        _sleep(_POLL_SECS)
    if outcome == "exited":
        for t in threads:
            t.join()
    return "".join(out_lines), "".join(err_lines), outcome


# ── Cartoon 3D: a segmented render (TMDEV-185) ──────────────────────────────
#
# One `remotion render` of a whole Cartoon 3D Short hung silently part way on
# the GPU (the spike: a long render at ~1/3, most likely GPU memory as every
# tab accumulates every set's textures and a crossfade opens a second WebGL
# context). So a Cartoon 3D video renders in segments of CARTOON_CHUNK_FRAMES
# frames, each its own Remotion process with a fresh browser and the same
# stall watcher as any render, video only; the segments are joined without
# re-encoding and the soundtrack is muxed on afterwards: the synthesised mix
# (mcp/cartoon.py's cartoon_soundtrack, under the job's cartoon/ directory)
# when it is there and newer than the voice, else the voice alone.
#
# The job directory here is the renderer's own copy of the job, downloaded
# from the gateway (the bundle keeps each file's modification time, so the
# mix-versus-voice comparison still means what it did).
CARTOON_CHUNK_FRAMES = 450          # 15 s at 30 fps
CARTOON_CHUNK_ATTEMPTS = 2          # a segment that hangs or fails is tried once more, fresh
CARTOON_MIX = ("cartoon", "audio", "mix", "mix.wav")
CARTOON_SOURCE = ("cartoon", "source.json")          # what submit_render froze: mcp/cartoon.py's SOURCE_RECORD
GENERATED_DIR = REMOTION_DIR / "src" / "scenes" / "generated"   # keep in sync with mcp/cartoon.py's mix_file
# A mascot video's drawing code, staged beside its job files under public/<id>/
# and named to the composition by the mascotPath render prop.
MASCOT_CODE = "mascot.js"
FFMPEG_TIMEOUT_SECS = 900


def _cartoon_chunks(total_frames: int, size: int = CARTOON_CHUNK_FRAMES) -> list:
    """Inclusive frame ranges tiling [0, total_frames). A short tail (under a
    third of a segment) joins the segment before it rather than costing a
    browser of its own."""
    if total_frames <= 0:
        return []
    starts = list(range(0, total_frames, size))
    if len(starts) > 1 and total_frames - starts[-1] < size / 3:
        starts.pop()
    return [(a, (starts[i + 1] - 1) if i + 1 < len(starts) else total_frames - 1) for i, a in enumerate(starts)]


def _soundtrack_for(job_dir: Path, voice_path: Path) -> Path:
    """The audio to mux: the synthesised mix when it exists and is at least as
    new as the voice (a re-voiced video makes an older mix stale), else the voice."""
    try:
        # join_below refuses a symlink in any component on the way
        mix = tjobs.join_below(job_dir, *CARTOON_MIX)
        if mix.is_file() and not mix.is_symlink() and mix.stat().st_mtime >= voice_path.stat().st_mtime:
            return mix
    except (OSError, tjobs.UnsafePath):
        pass
    return voice_path


def _cartoon_source_error(video_id: str, job_dir: Path) -> str | None:
    """Why the video's generated source is not the tree submit_render froze
    (its fingerprint under the job, written when the beat gate had passed):
    it was edited since, a non-regular file sits in it, or there is no record
    at all (only submit_render queues a Cartoon 3D video, and it always
    writes one: a missing or replaced record is not rendered). None when the
    tree Remotion compiles is the frozen one: the shared generated tree for the
    built-in renderer, the copy staged from the bundle for a remote one."""
    try:
        # join_below refuses a symlink in any component on the way (a planted
        # `cartoon` link would redirect the record itself)
        record = tjobs.join_below(job_dir, *CARTOON_SOURCE)
        if record.is_symlink():
            return f"{'/'.join(CARTOON_SOURCE)} is a symlink; the record of the queued source must be a plain file"
        if not record.is_file():
            return (f"no record of the source that was queued ({'/'.join(CARTOON_SOURCE)} is missing): "
                    "the video must be queued by submit_render")
        frozen = json.loads(record.read_text(encoding="utf-8")).get("fingerprint")
        live = tjobs.source_fingerprint(tjobs.scene_dir(GENERATED_DIR, video_id))
    except tjobs.UnsafePath as e:
        return f"the generated source cannot be rendered: {e}"
    except (OSError, ValueError, AttributeError) as e:
        return f"the generated source could not be checked against the one that was queued: {e}"
    if not isinstance(frozen, str) or frozen != live:
        return ("the generated source changed after the beat gate passed and the video was queued; "
                "run cartoon_beat_gate again on the new source, then submit_render")
    return None


def _run_ffmpeg(argv: list, timeout: float, **kwargs) -> subprocess.CompletedProcess:
    """One ffmpeg step of a Cartoon 3D render, as a job process: started in a
    process group of its own through _spawn, so it is the job's live process
    and a stop from the gateway kills it (and a stopped job never starts it).
    Past `timeout` its group is killed and reaped and TimeoutExpired raised,
    as subprocess.run's timeout did."""
    proc = _spawn(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
                  **kwargs)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_group_and_reap(proc)
        try:
            proc.communicate(timeout=5)     # closes the pipes
        except (subprocess.TimeoutExpired, OSError, ValueError):
            pass
        raise
    return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)


def _render_cartoon(video_id: str, job_dir: Path, props: str, output_path: str, gl_argv: list, gl_env: dict,
                    timeout_secs: int, stall_secs: int, total_frames: int, voice_path: Path) -> tuple:
    """Render a Cartoon 3D video in segments and mux its soundtrack. Returns
    (outcome, detail): outcome "ok", "hung" (a segment stalled, or the whole
    render ran past timeout_secs: environmental, retried by the caller as a
    timeout is) or "failed" (Remotion or ffmpeg reported an error, the source
    is not the one that was queued, or the render could not be run at all).
    timeout_secs caps the whole render, every segment and retry included,
    as it caps an ordinary render. `job_dir` is the staged job: its
    cartoon/source.json and cartoon/audio/mix/mix.wav."""
    out_file = Path(output_path)
    work = out_file.parent / f".{video_id}.segments"
    tmp_out = out_file.with_name(f"{out_file.name}.tmp.mp4")
    deadline = _clock() + timeout_secs
    chunks = _cartoon_chunks(total_frames)
    if not chunks:
        return "failed", f"timeline.json has no frames to render (totalFrames {total_frames})"
    segments = []
    try:
        shutil.rmtree(work, ignore_errors=True)
        work.mkdir(parents=True, exist_ok=True)
        for a, b in chunks:
            # every segment bundles the live tree afresh: checked round each one
            err = _cartoon_source_error(video_id, job_dir)
            if err:
                return "failed", err
            seg = work / f"seg_{a:05d}-{b:05d}.mp4"
            last_err, hung = "", False
            for attempt in range(1, CARTOON_CHUNK_ATTEMPTS + 1):
                remaining = deadline - _clock()
                if remaining <= 0:
                    return "hung", f"frames {a}-{b}: the render ran past {timeout_secs}s in all"
                log.info(f"[{video_id}] rendering frames {a}-{b} (attempt {attempt}/{CARTOON_CHUNK_ATTEMPTS})",
                         extra={"video_id": video_id})
                proc = _spawn(
                    ["npx", "remotion", "render", "Composition", str(seg), "--props", props,
                     "--browser-executable-path", CHROMIUM_BIN, *gl_argv,
                     # two tabs: the post stack hung at the default concurrency on one shared GPU
                     "--concurrency=2", f"--frames={a}-{b}", "--muted"],
                    cwd=str(REMOTION_DIR), env={**os.environ, **gl_env},
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True)
                stdout, stderr, outcome = _wait_for_render(proc, remaining, stall_secs)
                if outcome != "exited":
                    _kill_group_and_reap(proc)
                    hung = True
                    last_err = (f"frames {a}-{b}: no progress for {stall_secs}s" if outcome == "stall"
                                else f"frames {a}-{b}: the render ran past {timeout_secs}s in all")
                    log.warning(f"[{video_id}] {last_err}", extra={"video_id": video_id})
                    continue
                if proc.returncode == 0 and seg.is_file() and seg.stat().st_size > 0:
                    segments.append(seg)
                    break
                hung = False
                last_err = f"frames {a}-{b}: " + ((stderr or stdout or "remotion exited %d" % proc.returncode).strip()[-2000:])
                log.warning(f"[{video_id}] segment failed: {last_err[-300:]}", extra={"video_id": video_id})
            else:
                return ("hung" if hung else "failed"), last_err
        err = _cartoon_source_error(video_id, job_dir)
        if err:
            return "failed", err
        # ffmpeg spends what is left of the same deadline, FFMPEG_TIMEOUT_SECS at most
        remaining = deadline - _clock()
        if remaining <= 0:
            return "hung", f"joining the segments: the render ran past {timeout_secs}s in all"
        list_file = work / "segments.txt"
        list_file.write_text("".join(f"file '{p.name}'\n" for p in segments), encoding="utf-8")
        silent = work / "video.mp4"
        joined = _run_ffmpeg(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                              "-c", "copy", str(silent)], min(FFMPEG_TIMEOUT_SECS, remaining), cwd=str(work))
        if joined.returncode != 0 or not silent.is_file():
            return "failed", f"joining the {len(segments)} segments failed: {(joined.stderr or joined.stdout).strip()[-800:]}"
        remaining = deadline - _clock()
        if remaining <= 0:
            return "hung", f"muxing the soundtrack: the render ran past {timeout_secs}s in all"
        audio = _soundtrack_for(job_dir, voice_path)
        muxed = _run_ffmpeg(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(audio),
                             "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                             "-shortest", "-movflags", "+faststart", str(tmp_out)], min(FFMPEG_TIMEOUT_SECS, remaining))
        if muxed.returncode != 0 or not tmp_out.is_file():
            tmp_out.unlink(missing_ok=True)
            return "failed", f"muxing the soundtrack failed: {(muxed.stderr or muxed.stdout).strip()[-800:]}"
        os.replace(tmp_out, out_file)
        return "ok", (f"{len(segments)} segments, "
                      + ("the synthesised soundtrack" if audio != voice_path else "the voice alone"))
    except subprocess.TimeoutExpired as e:
        if deadline - _clock() <= 0:
            return "hung", f"ffmpeg: the render ran past {timeout_secs}s in all"
        return "failed", f"ffmpeg did not finish: {e}"
    except OSError as e:
        # a missing executable, a full or vanished disk: a reportable failure
        # of this render, not the end of the renderer
        return "failed", f"the render could not be run: {e}"
    finally:
        shutil.rmtree(work, ignore_errors=True)
        try:
            tmp_out.unlink(missing_ok=True)
        except OSError:
            pass


# ── GPU rendering (TMDEV-178) ───────────────────────────────────────────────
#
# A GPU reaches this container only through the Compose override that
# `onboard.py --step gpu` writes (onboard/gpu.py), which also sets
# TUBEMATIC_GPU_UUID/_NAME and TUBEMATIC_HOST_GPUS. Being configured is not
# the same as working: a driver update, a missing toolkit capability, or a
# hand-run `docker compose up` that skipped the override all leave the
# environment variables saying "GPU" while Chromium gets none. So the GPU is
# used only after a probe, run with the exact flags a render gets, has shown
# Chromium's WebGL renderer string naming that GPU. Anything else renders on
# the CPU (remotion.config.ts's swangle) rather than failing the video.
#
# The GPU options, all measured in this image (Plane TMDEV-178):
# - browserExecutable /usr/bin/chromium: the image's Debian Chromium. Note the
#   CLI flag is --browser-executable; the --browser-executable-path every render
#   has always passed is not a Remotion flag and is ignored, so CPU renders use
#   the headless shell Remotion downloads on first use. Left as it is for the
#   CPU path (unchanged behaviour); the GPU path names Debian Chromium
#   properly, which renders on the GPU with nothing to download.
# - gl angle-egl: hardware GL through EGL. The other values either fail or stay
#   in software.
# - chromeMode chrome-for-testing: with a named browser this only switches it to
#   --headless=new. Old headless passes a one-tab probe but cannot create WebGL
#   contexts in several tabs at once, so a real three.js render fails in every
#   tab. NEVER on the CPU path: new headless in software is about 5x slower.
# - enableMultiprocessOnLinux: Remotion's default in 4.x already; stated so a
#   default change cannot put Chromium in --single-process, which disables the
#   GPU process.
# - __EGL_VENDOR_LIBRARY_FILENAMES: without it libglvnd may pick another EGL
#   vendor (Mesa, or an integrated GPU on a host that passes one in), and the
#   render still "works" on the wrong device.
GPU_GL_OPTIONS = {"gl": "angle-egl", "chromeMode": "chrome-for-testing",
                  "enableMultiprocessOnLinux": True, "browserExecutable": CHROMIUM_BIN}
# What a CPU render gets implicitly from remotion.config.ts (swangle) and the
# CLI's defaults. Spelled out because the probe driver uses the Node API,
# which does not read remotion.config.ts.
CPU_GL_OPTIONS = {"gl": "swangle", "chromeMode": "headless-shell",
                  "enableMultiprocessOnLinux": True, "browserExecutable": None}
GPU_GL_ENV = {"__EGL_VENDOR_LIBRARY_FILENAMES": "/usr/share/glvnd/egl_vendor.d/10_nvidia.json"}

GPU_PROBE_TIMEOUT_SECS = 180
GPU_PROBE_DRIVER = "gpu-probe/run-gpu-probe.mjs"

# Set only by _run_gpu_probe. False until a probe passes, so a renderer that has
# not probed yet renders on the CPU, never on an unverified GPU.
_gpu_verified = False


def _gpu_config() -> dict:
    """What the Compose override told this container. Empty uuid = no GPU."""
    try:
        host_gpus = json.loads(os.getenv("TUBEMATIC_HOST_GPUS") or "[]")
    except ValueError:
        host_gpus = []
    return {"uuid": os.getenv("TUBEMATIC_GPU_UUID", "").strip(),
            "name": os.getenv("TUBEMATIC_GPU_NAME", "").strip(),
            "host_gpus": host_gpus if isinstance(host_gpus, list) else []}


def _render_on_gpu() -> bool:
    return bool(_gpu_config()["uuid"]) and _gpu_verified


def _gl_options(on_gpu: bool) -> tuple[dict, dict]:
    """The browser/GL options and environment for one path. The single
    source: a render's flags (_gl_args) and the probe's driver config are both
    built from it, so the probe is evidence about exactly what a render runs."""
    if on_gpu:
        return dict(GPU_GL_OPTIONS), dict(GPU_GL_ENV)
    return dict(CPU_GL_OPTIONS), {}


def _gl_args(on_gpu: bool) -> tuple[list, dict]:
    """The extra `remotion render` argv and environment for one path. The CPU
    path adds nothing, so a CPU render's command is what it always was."""
    options, env = _gl_options(on_gpu)
    if not on_gpu:
        return [], env
    return [f"--gl={options['gl']}", f"--chrome-mode={options['chromeMode']}",
            "--enable-multiprocess-on-linux",
            f"--browser-executable={options['browserExecutable']}"], env


def _judge_probe(webgl: dict | None, expected_name: str) -> tuple[bool, str]:
    """Did Chromium's WebGL land on the configured NVIDIA GPU?

    The renderer string, never "the render succeeded": the wrong device
    renders successfully too. It must name NVIDIA and the configured GPU, so
    SwiftShader, llvmpipe/Mesa and an integrated GPU all fail."""
    if not webgl:
        return False, "the probe produced no result (see the renderer log)"
    if not webgl.get("webgl"):
        return False, webgl.get("error") or "Chromium could not create a WebGL context"
    renderer = str(webgl.get("renderer") or "")
    if "nvidia" not in renderer.lower():
        return False, f"Chromium is rendering on another device: {renderer or 'unknown'}"
    if expected_name and expected_name.lower() not in renderer.lower():
        return False, f"Chromium got a different NVIDIA GPU than the configured {expected_name}"
    return True, ""


def _nvidia_smi(uuid_: str) -> dict:
    """Driver, memory and name of the configured GPU as seen inside this
    container. Informational: the probe's renderer string decides."""
    try:
        r = subprocess.run(
            ["nvidia-smi", f"--id={uuid_}", "--query-gpu=name,driver_version,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as e:
        return {"error": f"nvidia-smi did not run: {e}"}
    if r.returncode != 0:
        return {"error": (r.stderr or r.stdout).strip()[-300:] or "nvidia-smi failed"}
    parts = [p.strip() for p in r.stdout.strip().splitlines()[0].split(",")] if r.stdout.strip() else []
    if len(parts) < 3:
        return {"error": "nvidia-smi gave no row for the configured GPU"}
    return {"name": ", ".join(parts[:-2]), "driver": parts[-2],
            "memory_mib": int(parts[-1]) if parts[-1].isdigit() else None}


# How long the reaper waits for a SIGKILLed render's orphans to finish exiting.
# SIGKILL guarantees they do; a Chromium tearing down many threads takes
# seconds, not minutes, so this only bounds a kernel that is not cooperating.
REAP_TIMEOUT_SECS = 60


def _other_children() -> set[int]:
    """PIDs of this process's children other than the stills server, read
    from /proc: the orphans a killed process group reparented to us."""
    me = os.getpid()
    skip = _stills_proc.pid if _stills_proc is not None else None
    kids: set[int] = set()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return kids
    for d in entries:
        if not d.isdigit() or int(d) == skip:
            continue
        try:
            with open(f"/proc/{d}/stat") as fh:
                after_comm = fh.read().rsplit(")", 1)[1].split()
        except (OSError, IndexError):
            continue
        if len(after_comm) > 1 and after_comm[1] == str(me):
            kids.add(int(d))
    return kids


def _kill_group_and_reap(proc: subprocess.Popen) -> None:
    """SIGKILL a start_new_session child's whole process group and reap
    everything it left behind. Shared by the render and the GPU probe, which
    both run `npx remotion` (npx → node → Chromium → ffmpeg), and by a stop
    the gateway asked for (from the heartbeat thread)."""
    os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
    proc.wait()  # reaps our direct child (npx)
    # killpg's SIGKILL hits the whole group at once, but grandchildren
    # (node, chrome-headless, ffmpeg, ...) reparent to this container's
    # PID 1 -- this same renderer process -- the instant their own parent dies,
    # before proc.wait() can claim them by PID. Confirmed live (TMDEV-57
    # follow-up): SIGKILL guarantees they'll all exit but not instantly --
    # heavier processes (a Chromium instance tearing down many threads) can
    # take noticeably longer to actually finish than the lightweight npx
    # wrapper proc.wait() above already reaped. A single non-blocking drain
    # races ahead of that and finds nothing (confirmed live), and a blocking
    # waitpid(-1, 0) loop, which this used to be, would never return now that
    # the stills server (TMDEV-179) is a long-lived child of ours: it would
    # sit waiting for a healthy process. So: drain non-blocking, and keep
    # draining while a child other than the stills server is still alive.
    deadline = time.monotonic() + REAP_TIMEOUT_SECS
    while time.monotonic() < deadline:
        try:
            pid, _ = os.waitpid(-1, os.WNOHANG)
        except ChildProcessError:
            return
        if pid:
            continue
        if not _other_children():
            return
        time.sleep(0.05)
    log.warning("reaping the killed render's processes gave up after "
                f"{REAP_TIMEOUT_SECS} s; {len(_other_children())} still alive")


def _run_gpu_probe(reason: str) -> dict:
    """Render the GpuProbe still with a render's options, judge the renderer
    string, set _gpu_verified and return the result (the gateway stores it,
    from the next heartbeat, for the dashboard and the GPU gates).

    Runs even with no GPU configured: then it uses the CPU flags, and the
    software renderer string it reports is what the dashboard's Test button
    shows. Never raises — the render loop must survive a broken probe."""
    global _gpu_verified
    cfg = _gpu_config()
    configured = bool(cfg["uuid"])
    started = _now_precise()
    result = {"at": started, "reason": reason, "configured": configured,
              "gpu": {"uuid": cfg["uuid"], "name": cfg["name"]} if configured else None,
              "host_gpus": cfg["host_gpus"], "renderer": "", "vendor": "",
              "ok": False, "error": "", "secs": None, "smi": None}
    t0 = time.monotonic()
    try:
        options, gl_env = _gl_options(configured)
        out_json = Path("/tmp") / f"tubematic-gpu-probe-{uuid.uuid4().hex}.json"
        proc = subprocess.Popen(
            ["node", GPU_PROBE_DRIVER, json.dumps({**options, "outputPath": str(out_json)})],
            cwd=str(REMOTION_DIR), env={**os.environ, **gl_env},
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=True,
        )
        timed_out = False
        try:
            stdout, stderr = proc.communicate(timeout=GPU_PROBE_TIMEOUT_SECS)
        except subprocess.TimeoutExpired:
            _kill_group_and_reap(proc)
            stdout, stderr, timed_out = "", "", True
        # The answer is a file, never stdout: Remotion prints every page
        # console line there too (see the driver's header).
        try:
            webgl = json.loads(out_json.read_text())
        except (OSError, ValueError):
            webgl = None
        finally:
            out_json.unlink(missing_ok=True)
        if not isinstance(webgl, dict):
            webgl = None
        if webgl:
            result["renderer"] = str(webgl.get("renderer") or "")
            result["vendor"] = str(webgl.get("vendor") or "")
        if configured:
            result["ok"], result["error"] = _judge_probe(webgl, cfg["name"])
            result["smi"] = _nvidia_smi(cfg["uuid"])
        elif webgl and not webgl.get("webgl"):
            result["error"] = str(webgl.get("error") or "")
        if webgl is None:
            # Say what actually happened rather than "no result": a hang, or
            # the tail of whatever the driver printed before dying.
            tail = (stderr or stdout).strip()[-300:]
            result["error"] = (f"the probe did not finish within {GPU_PROBE_TIMEOUT_SECS}s"
                               if timed_out else
                               f"the probe produced no result: {tail or 'no output'}")
            log.warning(f"GPU probe produced no result: {(stderr or stdout)[-2000:]}")
    except Exception as e:  # noqa: BLE001 — a broken probe must not stop the renderer
        log.exception("GPU probe failed")
        result["error"] = f"the probe could not run: {e}"
    result["secs"] = round(time.monotonic() - t0, 1)

    was = _gpu_verified
    _gpu_verified = configured and result["ok"]
    if configured and _gpu_verified:
        log.info(f"GPU probe ({reason}): rendering on {cfg['name']} — {result['renderer']}")
    elif configured:
        # WARNING, logged on every failed probe: renders still succeed on the
        # CPU, so this line is how a slow-but-working install finds out why.
        log.warning(f"GPU probe ({reason}): {cfg['name']} is configured but not usable "
                    f"({result['error']}) — rendering on the CPU")
    if was and not _gpu_verified:
        log.warning("GPU rendering stopped: renders fall back to the CPU until a probe passes")
    return result


def _probe_and_queue(reason: str) -> dict:
    """Run the probe and keep its result for the next heartbeat to carry."""
    result = _run_gpu_probe(reason)
    with _st.lock:
        _st.pending_probe = result
    return result


# ── The stills server (TMDEV-179) ───────────────────────────────────────────
#
# The MCP container's Cartoon 3D tools need stills of a video's composition
# (the part gate, the beat gate, the author's own previews), and this is the
# one container with the GPU. So the renderer runs cartoon-tools/stills-server.mjs
# beside its renders: bundled once, one browser, a still in a few seconds
# instead of the ~30 s a cold software-GL still costs in the MCP container.
# It gets exactly the GL options a render gets (_gl_options), so a passing
# probe moves it onto the GPU and a failing one moves it back, and it serves
# the shared /jobs volume as its public directory so a video's files are
# /public/<vid>/... with nothing staged. Compose-network only; never published.
# The built-in renderer only: a remote renderer has no /jobs volume.
STILLS_SERVER_PORT = int(os.getenv("TUBEMATIC_STILLS_PORT", "0") or "0")   # 0: do not run one
STILLS_SERVER_SCRIPT = "cartoon-tools/stills-server.mjs"
STILLS_SERVER_HOST = "0.0.0.0"
# A server that dies is started again, but not in a tight loop: a Chromium
# that cannot open is retried every so often, not every pass of the loop.
STILLS_SERVER_RETRY_SECS = 60

_stills_proc = None
_stills_on_gpu: bool | None = None
_stills_started_at = 0.0


def _stills_server_argv(on_gpu: bool) -> tuple[list, dict]:
    """The command and environment for one GL path: the same options as a
    render's, spelled as the server's flags."""
    options, env = _gl_options(on_gpu)
    argv = ["node", STILLS_SERVER_SCRIPT, "--port", str(STILLS_SERVER_PORT), "--host", STILLS_SERVER_HOST,
            "--public", JOBS_DIR, "--gl", options["gl"], "--chrome-mode", options["chromeMode"],
            "--multiprocess", "1" if options["enableMultiprocessOnLinux"] else "0"]
    if options.get("browserExecutable"):
        argv += ["--browser-executable", options["browserExecutable"]]
    return argv, env


def _stop_stills_server() -> None:
    global _stills_proc
    proc = _stills_proc
    _stills_proc = None
    if proc is None or proc.poll() is not None:
        return
    try:
        os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        proc.wait(timeout=15)
    except Exception:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except Exception:
            pass


def _ensure_stills_server(now: float | None = None) -> None:
    """Start the server, or start it again when it has died or when the GL
    path it was started on no longer matches what renders use. One pass of the
    render loop, so never blocking."""
    global _stills_proc, _stills_on_gpu, _stills_started_at
    if not STILLS_SERVER_PORT:
        return
    now = time.monotonic() if now is None else now
    on_gpu = _render_on_gpu()
    alive = _stills_proc is not None and _stills_proc.poll() is None
    if alive and _stills_on_gpu == on_gpu:
        return
    if alive:
        log.info(f"stills server: GL path changed ({'GPU' if on_gpu else 'CPU'}), starting it again")
        _stop_stills_server()
    elif _stills_proc is not None:
        log.warning(f"stills server exited with {_stills_proc.returncode}; starting it again")
        _stills_proc = None
    if now - _stills_started_at < STILLS_SERVER_RETRY_SECS and _stills_on_gpu == on_gpu:
        return
    argv, extra_env = _stills_server_argv(on_gpu)
    try:
        _stills_proc = subprocess.Popen(
            argv, cwd=str(REMOTION_DIR), env={**os.environ, **extra_env},
            stdin=subprocess.DEVNULL, stdout=None, stderr=None, start_new_session=True)
    except Exception:
        log.exception("stills server could not start")
        _stills_proc = None
    _stills_on_gpu = on_gpu
    _stills_started_at = now
    if _stills_proc is not None:
        log.info(f"stills server started on the {'GPU' if on_gpu else 'CPU'} path, port {STILLS_SERVER_PORT}")


# ── Who this renderer is, and how it reaches the gateway (TMDEV-189) ─────────
#
# The gateway's certificate is self-signed and names no host (renderers reach
# it by whatever address the operator gives them), so a renderer trusts
# exactly that one certificate and nothing else: no system CA, no host name
# check. The built-in renderer gets the certificate as a secret file; a remote
# one learns it once, at enrollment, from the server itself, and keeps it only
# after its sha256 matched the pin the enrollment token carried.

BUILTIN_TOKEN_NAME = "builtin_renderer_token"
STATE_FILE_NAME = "renderer.json"
DEFAULT_GATEWAY_URL = "https://tubematic-api:4443"
# A per-job directory of the renderer's own: the bundle is unpacked here and
# the render is written here, so nothing a job leaves behind outlives it.
RENDER_TMP = Path(os.getenv("TUBEMATIC_RENDER_TMP", "/tmp/tubematic-render"))
OUTPUT_NAME = "output.mp4"
NETWORK_RETRY_SECS = 30
ENROLL_RETRY_SECS = 60
UPLOAD_ATTEMPTS = 3
# How long an upload waits on a gateway that answers busy (all its upload
# slots taken, or this claim's earlier attempt still being received) before
# the render is reported as an error. Waiting costs nothing but the lease's
# heartbeats; giving up throws a finished render away.
UPLOAD_WAIT_SECS = 2 * 3600
RESULT_ATTEMPTS = 3
RETRY_PAUSE_SECS = 5
MAX_RETRY_AFTER_SECS = 60
# A result's error, at most: even escaped six bytes a character it stays
# under the gateway's 64 KiB JSON limit, and the comment it becomes keeps
# only its first 2000 characters.
RESULT_ERROR_CHARS = 8000
CONNECT_TIMEOUT_SECS = 30
# Generous read/write timeouts: a bundle with many images, or a long video's
# upload over a home connection, moves hundreds of megabytes.
REQUEST_TIMEOUT = httpx.Timeout(30.0, read=300.0, write=300.0)
STREAM_CHUNK = 1 << 20


def _is_builtin() -> bool:
    return os.getenv("TUBEMATIC_RENDERER_BUILTIN", "").strip() == "1"


def _state_file() -> Path:
    return Path(os.getenv("TUBEMATIC_RENDERER_STATE", "/state")) / STATE_FILE_NAME


def pinned_context(cert_pem: str) -> ssl.SSLContext:
    """A client TLS context that trusts exactly `cert_pem`: the gateway's own
    certificate is the only trust anchor, and there is no host name to check."""
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    ctx.load_verify_locations(cadata=cert_pem)
    return ctx


def _pem_pin(cert_pem: str) -> str:
    return renderers.cert_pin(ssl.PEM_cert_to_DER_cert(cert_pem))


class GatewayError(Exception):
    """The gateway could not be reached, or answered something unusable.
    `status` is the HTTP status when there was an answer, `error` its error
    code ({"error": ...}) when it gave one."""

    def __init__(self, message: str, status: int | None = None, error: str = ""):
        super().__init__(message)
        self.status = status
        self.error = error


class EnrollmentError(Exception):
    """This renderer cannot become (or stay) a renderer of this install as
    configured: no token, a bad or used token, a certificate that is not the
    pinned one. Retrying the same configuration later is harmless."""


class BuiltinIdentity:
    """The built-in renderer: its credential and the gateway's certificate are
    secret files, read on every request, so `--rotate-tokens` applies to the
    next request with no restart."""
    builtin = True
    renderer_id = renderers.BUILTIN_ID

    def url(self) -> str:
        return (os.getenv("TUBEMATIC_GATEWAY_URL") or DEFAULT_GATEWAY_URL).rstrip("/")

    def credential(self) -> str:
        return tauth.read_secret(BUILTIN_TOKEN_NAME)

    def cert_pem(self) -> str:
        return tauth.read_secret(tauth.TLS_CERT_NAME)

    def save_rotated(self, credential: str, expires_at: str) -> None:
        # The gateway never rotates the built-in token (it is the secret
        # file); one arriving anyway is not ours to keep.
        log.warning("the gateway sent the built-in renderer a rotated credential; ignored")


class RemoteIdentity:
    """A remote renderer: the state file written at enrollment holds its id,
    credential, machine id, the pinned certificate and the gateway address.
    TUBEMATIC_GATEWAY_URL, when set, overrides the address (main moved), never
    the certificate."""
    builtin = False

    def __init__(self, path: Path, data: dict):
        self.path = path
        self.data = data
        self._lock = threading.Lock()

    @property
    def renderer_id(self) -> str:
        return self.data.get("renderer_id") or ""

    def url(self) -> str:
        return (os.getenv("TUBEMATIC_GATEWAY_URL") or self.data.get("gateway_url") or "").rstrip("/")

    def credential(self) -> str:
        with self._lock:
            return self.data.get("credential") or ""

    def cert_pem(self) -> str:
        return self.data.get("cert_pem") or ""

    def save_rotated(self, credential: str, expires_at: str) -> None:
        """Keep a rotated credential. The new one is used only once it is on
        disk: the gateway forgets the old one the moment the new one is first
        used, so switching before the save landed would leave a restarted
        renderer holding a credential nothing accepts."""
        with self._lock:
            new = {**self.data, "credential": credential, "credential_expires_at": expires_at or ""}
            try:
                _write_state(self.path, new)
            except OSError as e:
                log.error(f"a rotated credential could not be saved ({e}); keeping the current one, "
                          "which stays valid until the new one is used")
                return
            self.data = new
        log.info("saved a rotated renderer credential")


def _write_state(path: Path, data: dict) -> None:
    """Write the state file atomically (a temp file beside it, fsync'd, renamed
    over it), readable by this user only: it holds the credential."""
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    finally:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass


def _load_state(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, ValueError) as e:
        log.error(f"the renderer state file {path} cannot be read ({e})")
        return None
    return data if isinstance(data, dict) else None


def _token_hash(secret: str) -> str:
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()


class GatewayClient:
    """HTTP to the gateway through the pinned context. A fresh connection per
    call: a heartbeat every 30 s and a claim every 20 s cost nothing worth
    pooling, and each call re-reads the credential and certificate (a rotation
    applies at once). `transport` is for tests only (an httpx WSGITransport
    over the gateway app); TLS is then not involved."""

    def __init__(self, identity, transport=None):
        self.identity = identity
        self.transport = transport

    def _headers(self, auth: bool) -> dict:
        if not auth:
            return {}
        try:
            credential = self.identity.credential()
        except tauth.SecretMissing as e:
            raise GatewayError(f"the renderer's credential cannot be read: {e}") from None
        if not credential:
            raise GatewayError("the renderer has no credential")
        return {"Authorization": f"Bearer {credential}"}

    def _http(self, timeout) -> httpx.Client:
        url = self.identity.url()
        if not url:
            raise GatewayError("no gateway address is configured")
        if self.transport is not None:
            return httpx.Client(base_url=url, transport=self.transport, timeout=timeout)
        try:
            ctx = pinned_context(self.identity.cert_pem())
        except (tauth.SecretMissing, ssl.SSLError, ValueError) as e:
            raise GatewayError(f"the gateway's certificate cannot be loaded: {e}") from None
        return httpx.Client(base_url=url, verify=ctx, timeout=timeout)

    def send(self, method: str, path: str, *, json_body=None, content=None, auth: bool = True,
             timeout=REQUEST_TIMEOUT, headers=None) -> httpx.Response:
        """One request; the response whatever its status. GatewayError when
        there was no answer at all."""
        headers = {**self._headers(auth), **(headers or {})}
        try:
            with self._http(timeout) as http:
                return http.request(method, path, json=json_body, content=content, headers=headers)
        except httpx.HTTPError as e:
            raise GatewayError(f"{method} {path}: {type(e).__name__}: {e}") from None

    @contextmanager
    def stream(self, method: str, path: str, timeout=REQUEST_TIMEOUT, headers=None):
        headers = {**self._headers(True), **(headers or {})}
        try:
            with self._http(timeout) as http:
                with http.stream(method, path, headers=headers) as resp:
                    yield resp
        except httpx.HTTPError as e:
            raise GatewayError(f"{method} {path}: {type(e).__name__}: {e}") from None


def _error_code(resp: httpx.Response) -> str:
    try:
        body = resp.json()
    except ValueError:
        return ""
    return str(body.get("error") or "") if isinstance(body, dict) else ""


def _job_path(video_id: str, tail: str) -> str:
    return f"/v1/jobs/{urllib.parse.quote(video_id, safe='')}/{tail}"


# Every job route names the claim it acts for: the gateway refuses the
# bundle, the upload and the result of a claim the renderer no longer holds,
# even when it has claimed the same video again since.
CLAIM_HEADER = "X-Render-Claim"


def _job_headers(job) -> dict:
    return {CLAIM_HEADER: job.claim_id}


# ── Enrollment ───────────────────────────────────────────────────────────────

def _fetch_server_cert(host: str, port: int) -> str:
    """The certificate the server at host:port presents, as PEM. A TLS
    handshake only: no request is sent."""
    return ssl.get_server_certificate((host, port), timeout=CONNECT_TIMEOUT_SECS)


def _renderer_name() -> str:
    return (os.getenv("TUBEMATIC_RENDERER_NAME") or "").strip() or socket.gethostname()


def enroll(token: str, state_path: Path, compute: dict, transport=None) -> RemoteIdentity:
    """Redeem an enrollment token: learn the gateway's certificate, refuse it
    unless its sha256 is the token's pin (before anything is sent), then
    exchange the one-time secret for a credential and save the state file.

    Re-enrolling keeps the machine id of an existing state file, which is what
    makes the gateway replace this machine's row rather than add one."""
    try:
        tok = renderers.decode_enrollment_token(token)
    except ValueError as e:
        raise EnrollmentError(f"TUBEMATIC_ENROLL_TOKEN is not usable: {e}") from None
    parts = urllib.parse.urlsplit(tok["url"])
    if not parts.hostname:
        raise EnrollmentError("the enrollment token's gateway address has no host")
    try:
        pem = _fetch_server_cert(parts.hostname, parts.port or 443)
        got = _pem_pin(pem)
    except (OSError, ValueError) as e:
        raise GatewayError(f"the gateway at {tok['url']} could not be reached: {e}") from None
    if not hmac.compare_digest(got, tok["pin"]):
        raise EnrollmentError(
            f"the server at {tok['url']} presented a certificate ({got}) that is not the one the "
            f"enrollment token pins ({tok['pin']}); nothing was sent to it. Check the address, or "
            "issue a new token on the main machine")
    existing = _load_state(state_path) or {}
    data = {"renderer_id": "", "credential": "", "credential_expires_at": "",
            "machine_id": existing.get("machine_id") or uuid.uuid4().hex,
            "pin": tok["pin"], "cert_pem": pem, "gateway_url": tok["url"].rstrip("/")}
    if not existing.get("machine_id"):
        # kept before the secret is spent, so a retry after a lost reply
        # still enrolls as the same machine
        _write_state(state_path, {**existing, "machine_id": data["machine_id"]})
    identity = RemoteIdentity(state_path, data)
    client = GatewayClient(identity, transport)
    resp = client.send("POST", "/v1/enroll", auth=False, json_body={
        "secret": tok["secret"], "machine_id": data["machine_id"], "name": _renderer_name(),
        "host": socket.gethostname(), "version": current_version(), "compute": compute})
    if resp.status_code == 403:
        log.error("the gateway refused the enrollment (enrollment_invalid): the token is unknown, already "
                  "used or expired")
        raise EnrollmentError("the gateway refused the enrollment token: it is unknown, already used or "
                              "expired. Issue a new one on the main machine")
    if resp.status_code != 200:
        raise GatewayError(f"enrollment answered {resp.status_code} {_error_code(resp)}".strip(),
                           resp.status_code, _error_code(resp))
    out = resp.json()
    data.update(renderer_id=out.get("renderer_id") or "", credential=out.get("credential") or "",
                credential_expires_at=out.get("credential_expires_at") or "",
                enrolled_with=_token_hash(tok["secret"]))
    if not data["credential"]:
        raise GatewayError("enrollment answered without a credential")
    _write_state(state_path, data)
    # The remote host script watches the log for "enrolled" (and, below, for
    # "first heartbeat", "enrollment_invalid", "credential expired" and
    # "needs upgrade"): keep those words in these lines.
    log.info(f"enrolled as renderer {data['renderer_id']} with the gateway at {data['gateway_url']}")
    return identity


def _load_identity(compute: dict, transport=None):
    """Who this renderer is: the built-in one, or the remote one its state
    file names, enrolling first when a token is given that it has not
    redeemed yet (a first start, or a re-enrollment after its credential
    expired). Raises EnrollmentError or GatewayError when it cannot be either."""
    if _is_builtin():
        return BuiltinIdentity()
    path = _state_file()
    data = _load_state(path)
    usable = bool(data and data.get("credential") and data.get("cert_pem") and data.get("pin"))
    token = (os.getenv("TUBEMATIC_ENROLL_TOKEN") or "").strip()
    if token:
        try:
            secret = renderers.decode_enrollment_token(token)["secret"]
        except ValueError:
            secret = None
        if not usable or secret is None or data.get("enrolled_with") != _token_hash(secret):
            try:
                return enroll(token, path, compute, transport)
            except EnrollmentError as e:
                if not usable:
                    raise
                log.warning(f"{e}; carrying on with the credential already saved in {path}")
    if not usable:
        raise EnrollmentError(f"this renderer is not enrolled ({path} holds no credential): start it with "
                              "TUBEMATIC_ENROLL_TOKEN set to a token issued on the main machine")
    try:
        if _pem_pin(data["cert_pem"]) != data["pin"]:
            raise ValueError("the saved certificate does not match the saved pin")
    except ValueError as e:
        raise EnrollmentError(f"{path} is damaged ({e}): enroll again with a new token") from None
    return RemoteIdentity(path, data)


# ── What this renderer is, for the gateway's scheduler ────────────────────────

def _gpus() -> list:
    """The GPUs this renderer can see: every one nvidia-smi lists (when the
    container has it), and the configured one even when it does not."""
    gpus = []
    if shutil.which("nvidia-smi"):
        try:
            r = subprocess.run(["nvidia-smi", "--query-gpu=name,uuid,memory.total",
                                "--format=csv,noheader,nounits"], capture_output=True, text=True, timeout=20)
            rows = r.stdout.strip().splitlines() if r.returncode == 0 else []
        except (OSError, subprocess.TimeoutExpired):
            rows = []
        for row in rows:
            parts = [p.strip() for p in row.split(",")]
            if len(parts) >= 3:
                gpus.append({"name": ", ".join(parts[:-2]), "uuid": parts[-2],
                             "memory_mb": int(parts[-1]) if parts[-1].isdigit() else None})
    cfg = _gpu_config()
    if cfg["uuid"] and not any(g["uuid"] == cfg["uuid"] for g in gpus):
        gpus.append({"name": cfg["name"], "uuid": cfg["uuid"], "memory_mb": None})
    return gpus


def _compute_report() -> dict:
    memory = 0
    try:
        with open("/proc/meminfo") as fh:
            for line in fh:
                if line.startswith("MemTotal:"):
                    memory = int(line.split()[1]) * 1024
                    break
    except (OSError, ValueError, IndexError):
        pass
    return {"cpus": os.cpu_count() or 1, "memory_bytes": memory, "gpus": _gpus()}


# ── Shared state between the loop and the heartbeat thread ───────────────────

class _Job:
    """The render in progress, and the claim (`claim_id`) it renders under.
    `proc` is its current process (Remotion, or a Cartoon 3D ffmpeg step), so a
    stop from the gateway can kill it; `stopped` tells the loop to throw the
    render away without reporting a result."""

    def __init__(self, video_id: str, claim_id: str = ""):
        self.video_id = video_id
        self.claim_id = claim_id
        self.lock = threading.Lock()
        self.proc = None
        self.stopped = False


class _AgentState:
    def __init__(self):
        self.lock = threading.Lock()
        self.started = True          # until a heartbeat saying so got through
        self.enabled = False
        self.needs_upgrade = False
        self.probe_now = False
        self.last_error = ""
        self.pending_probe = None    # a probe result no heartbeat has carried yet
        self.job = None
        self.compute = {}


_st = _AgentState()
_client: GatewayClient | None = None
_beat_lock = threading.Lock()


class _Stopped(Exception):
    """The gateway no longer wants this render (heartbeat `stop`)."""


class _LeaseLost(Exception):
    """The gateway says this renderer does not hold the video any more."""


class _BundleUnavailable(Exception):
    """The gateway cannot bundle the job's files (409)."""


class _BundleRefused(Exception):
    """The bundle holds a member the renderer will not unpack."""


CREDENTIAL_EXPIRED_MESSAGE = ("credential expired: the gateway refused this renderer's credential. Enroll it "
                              "again with a new token (TUBEMATIC_ENROLL_TOKEN)")


def _note_error(message: str) -> None:
    """A renderer-level problem (not a video's own render failure): logged,
    and reported as last_error by every heartbeat until a claim succeeds."""
    log.warning(message)
    with _st.lock:
        _st.last_error = message[:2000]


def _spawn(argv, **kwargs) -> subprocess.Popen:
    """Popen for a render process, registered on the current job under its
    lock, so a stop either happens before the process exists (and refuses to
    start it) or finds it to kill: there is no window between the two."""
    job = _st.job
    if job is None:
        return subprocess.Popen(argv, **kwargs)
    with job.lock:
        if job.stopped:
            raise _Stopped()
        proc = subprocess.Popen(argv, **kwargs)
        job.proc = proc
    return proc


def _stop_job(job: _Job) -> None:
    """Stop the render the gateway no longer wants: kill its process group
    (the same reaper a stalled render gets) and mark it so the loop discards
    it. Runs on the heartbeat thread."""
    with job.lock:
        if job.stopped:
            return
        job.stopped = True
        proc = job.proc
    log.warning(f"[{job.video_id}] the gateway no longer wants this render; stopping it",
                extra={"video_id": job.video_id})
    if proc is not None and proc.poll() is None:
        try:
            _kill_group_and_reap(proc)
        except Exception:  # noqa: BLE001 — already gone, or a reap that failed: the loop discards either way
            log.exception(f"[{job.video_id}] killing the stopped render failed", extra={"video_id": job.video_id})


# ── The heartbeat ─────────────────────────────────────────────────────────────

def _beat() -> bool:
    """One heartbeat. True when it got through. Serialized: the loop sends
    one itself (the first, and one after a probe) beside the thread's."""
    with _beat_lock:
        with _st.lock:
            job = _st.job
            probe = _st.pending_probe
            body = {"started": _st.started, "version": current_version(), "compute": _st.compute,
                    "state": "rendering" if job is not None else "idle",
                    "video_id": job.video_id if job is not None else "",
                    "claim_id": job.claim_id if job is not None else "",
                    "last_error": _st.last_error}
        if probe is not None:
            body["gpu_probe"] = probe
        try:
            resp = _client.send("POST", "/v1/heartbeat", json_body=body)
        except GatewayError as e:
            _note_error(f"heartbeat failed: {e}")
            return False
        if resp.status_code != 200:
            code = _error_code(resp)
            if code == "credential_expired":
                _note_error(CREDENTIAL_EXPIRED_MESSAGE)
            else:
                _note_error(f"heartbeat answered {resp.status_code} {code}".strip())
            return False
        try:
            reply = resp.json()
        except ValueError:
            reply = None
        if not isinstance(reply, dict):
            _note_error("heartbeat answered with no JSON body")
            return False
        if body["started"]:
            log.info(f"first heartbeat accepted by main {reply.get('main_version') or 'of an unknown version'}")
        with _st.lock:
            _st.started = False
            if _st.pending_probe is probe:
                _st.pending_probe = None
            _st.enabled = reply.get("enabled") is True
            was_behind, _st.needs_upgrade = _st.needs_upgrade, reply.get("needs_upgrade") is True
            if reply.get("probe_now") is True:
                _st.probe_now = True
        if _st.needs_upgrade and not was_behind:
            log.warning(f"this renderer needs upgrade: it runs {current_version()}, main runs "
                        f"{reply.get('main_version')}, and it takes no work until it is upgraded")
        credential = reply.get("credential")
        # Saved before the lock is let go: a second heartbeat sent with the
        # old credential while this one is still unsaved would be issued
        # another replacement, and whichever save landed last could be one the
        # gateway no longer accepts. The other requests never rotate.
        if isinstance(credential, str) and credential:
            _client.identity.save_rotated(credential, str(reply.get("credential_expires_at") or ""))
    # The stop list names claims. It answers the request that was sent, so it
    # is applied to the job that request reported — never to whatever job is
    # current by the time the reply arrives: that may be a newer claim of the
    # same video, started while this reply was delayed, which the gateway
    # still wants. Entries for anything else (a stale row it once held) are
    # ignored.
    stop = reply.get("stop") if isinstance(reply.get("stop"), list) else []
    if job is not None and any(isinstance(e, dict) and e.get("video_id") == job.video_id
                               and e.get("claim_id") == job.claim_id for e in stop):
        _stop_job(job)
    return True


_hb_stop = threading.Event()


def _heartbeat_loop(stop_event: threading.Event) -> None:
    while not stop_event.wait(renderers.HEARTBEAT_SECS):
        try:
            _beat()
        except Exception:  # noqa: BLE001 — the thread must outlive any one beat
            log.exception("heartbeat failed")


def _start_heartbeat_thread() -> threading.Thread:
    t = threading.Thread(target=_heartbeat_loop, args=(_hb_stop,), name="heartbeat", daemon=True)
    t.start()
    return t


# ── A job: bundle in, mp4 out ─────────────────────────────────────────────────

FLAT_SCENES = "_flat"
_BUNDLE_FILES = {tjobs.AUDIO, tjobs.TIMELINE, tjobs.SCENE_CONFIG, MASCOT_CODE,
                 "/".join(CARTOON_SOURCE), "/".join(CARTOON_MIX)}


def _bundle_parts(name, video_id: str) -> list:
    """A bundle member's path components, or _BundleRefused. Only the names
    the gateway sends, and nothing that could land outside the job directory:
    no absolute path, no "..", "." or empty component, no backslash."""
    if (not isinstance(name, str) or not name or name.startswith("/") or "\\" in name or "\0" in name):
        raise _BundleRefused(f"the bundle holds a member with an unusable name: {name!r}")
    parts = name.split("/")
    if any(p in ("", ".", "..") for p in parts):
        raise _BundleRefused(f"the bundle holds a member with an unusable name: {name!r}")
    if (name in _BUNDLE_FILES
            or (parts[0] == tjobs.IMAGES and len(parts) >= 2)
            or (parts[0] == "scenes" and len(parts) >= 3 and parts[1] == video_id)
            or (parts[0] == "scenes" and len(parts) == 3 and parts[1] == FLAT_SCENES
                and parts[2].endswith(".tsx"))):
        return parts
    raise _BundleRefused(f"the bundle holds a member the renderer does not expect: {name!r}")


class _ChunkReader:
    """A read()-able view of an iterator of byte chunks, for tarfile's stream mode."""

    def __init__(self, chunks):
        self._it = iter(chunks)
        self._buf = bytearray()

    def read(self, n=-1):
        while n is None or n < 0 or len(self._buf) < n:
            try:
                self._buf += next(self._it)
            except StopIteration:
                break
        if n is None or n < 0:
            n = len(self._buf)
        out = bytes(self._buf[:n])
        del self._buf[:n]
        return out


def _download_bundle(job: _Job, work: Path) -> None:
    """Stream the job's bundle and unpack it into `work`, one member at a time
    and never whole in memory. Every member is checked first (_bundle_parts),
    must be a regular file, and is created fresh (no overwrite, no symlink
    followed); each keeps its modification time."""
    vid = job.video_id
    with _client.stream("GET", _job_path(vid, "bundle"), headers=_job_headers(job)) as resp:
        if resp.status_code == 403:
            raise _LeaseLost("the gateway refused the bundle: this renderer does not hold the video any more")
        if resp.status_code == 409:
            resp.read()
            try:
                detail = resp.json().get("detail") or ""
            except ValueError:
                detail = ""
            raise _BundleUnavailable(detail or "the gateway cannot bundle the job's files")
        if resp.status_code != 200:
            resp.read()
            raise GatewayError(f"the bundle answered {resp.status_code} {_error_code(resp)}".strip(),
                               resp.status_code)
        with tarfile.open(fileobj=_ChunkReader(resp.iter_bytes(STREAM_CHUNK)), mode="r|") as tf:
            for member in tf:
                parts = _bundle_parts(member.name, vid)
                if not member.isreg():
                    raise _BundleRefused(f"the bundle member {member.name!r} is not a regular file")
                dest = work.joinpath(*parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                src = tf.extractfile(member)
                fd = os.open(dest, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
                with os.fdopen(fd, "wb") as fh:
                    shutil.copyfileobj(src, fh, STREAM_CHUNK)
                os.utime(dest, (member.mtime, member.mtime))
                if job.stopped:
                    raise _Stopped()
    missing = [n for n in tjobs.JOB_FILES if not (work / n).is_file()]
    if missing:
        raise _BundleRefused(f"the bundle has no {', '.join(missing)}")


def _clear_generated() -> None:
    """Empty this renderer's own generated-scene tree (a remote renderer: the
    image's copy). Remotion compiles every file under it into every render, so
    a scene left over from another job could break or leak into the next one.
    Never the built-in renderer's: that tree is the shared volume the agent
    writes, and refused for any mounted directory for the same reason."""
    if _is_builtin():
        return
    if os.path.ismount(GENERATED_DIR):
        raise RuntimeError(f"{GENERATED_DIR} is a mounted directory: a remote renderer stages each job's scenes "
                           "into its own copy and never clears a shared one")
    if not GENERATED_DIR.is_dir():
        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        return
    for entry in GENERATED_DIR.iterdir():
        if entry.name == ".gitkeep":
            continue
        if entry.is_dir() and not entry.is_symlink():
            shutil.rmtree(entry)
        else:
            entry.unlink()


def _stage(job: _Job, work: Path, public: Path) -> None:
    """The unpacked job into the Remotion public dir (and, on a remote
    renderer, its scenes into the generated tree), as the renderer always
    staged a job from /jobs. Symlinks are skipped for the same reason as
    before: copytree follows them."""
    public.mkdir(parents=True, exist_ok=True)
    for name in tjobs.JOB_FILES:
        shutil.copy(work / name, public / name)
    # Per-video generated images (TMDEV-29). Optional — most videos have none.
    # Scenes reference these as /public/<video_id>/images/<name>, which is
    # exactly what staticFile() would resolve to.
    if (work / tjobs.IMAGES).is_dir():
        shutil.copytree(work / tjobs.IMAGES, public / tjobs.IMAGES, dirs_exist_ok=True,
                        ignore=tjobs.ignore_symlinks)
    if (work / MASCOT_CODE).is_file():
        shutil.copy(work / MASCOT_CODE, public / MASCOT_CODE)
    if _is_builtin():
        return   # renders compile the shared generated tree, as they always did
    scenes = work / "scenes"
    tree = scenes / job.video_id
    if tree.is_dir():
        shutil.copytree(tree, tjobs.scene_dir(GENERATED_DIR, job.video_id), ignore=tjobs.ignore_symlinks)
    flat = scenes / FLAT_SCENES
    if flat.is_dir():
        for f in sorted(flat.iterdir()):
            if f.is_file() and not f.is_symlink() and f.suffix == ".tsx":
                shutil.copy(f, tjobs.scene_file(GENERATED_DIR, "", f.stem))


def _clean_job(work: Path | None, public: Path | None) -> None:
    for d in (work, public):
        if d is not None:
            shutil.rmtree(d, ignore_errors=True)
    try:
        _clear_generated()
    except Exception as e:  # noqa: BLE001 — cleanup must not mask the job's own outcome
        log.error(f"could not clear the staged scenes: {e}")


def _int_setting(settings: dict, key: str, default: int) -> int:
    try:
        value = int(settings.get(key, default))
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _total_frames(claim: dict, timeline_path: Path) -> int:
    frames = claim.get("total_frames")
    if isinstance(frames, int) and not isinstance(frames, bool) and frames > 0:
        return frames
    try:
        return int(json.loads(timeline_path.read_text(encoding="utf-8")).get("totalFrames", 0))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0


def _failure(outcome: str, error: str, on_gpu: bool, probe_reason: str) -> dict:
    """A failed or hung render's result. A GPU it rendered on is re-tested
    first: a GPU that stopped working (a driver update, a reset) fails every
    render after it, so the gateway needs the answer to route the video (a
    GPU-only video goes straight to FAILED) and to stop sending this renderer
    GPU work, and the next render here falls back to the CPU."""
    body = {"outcome": outcome, "error": error, "on_gpu": on_gpu, "gpu_ok": None}
    if on_gpu:
        probe = _probe_and_queue(probe_reason)
        body["gpu_ok"] = probe.get("ok") is True
        body["gpu_probe"] = probe
    return body


def _render(job: _Job, claim: dict, work: Path, public: Path) -> dict:
    """Render one staged job; the body of its result. A success has been
    uploaded already."""
    video_id = job.video_id
    settings = claim.get("settings") if isinstance(claim.get("settings"), dict) else {}
    timeout_secs = _int_setting(settings, "render_timeout_secs", 10800)
    stall_secs = _int_setting(settings, "render_stall_timeout_secs", 600)
    cartoon = claim.get("cartoon") is True
    needs_gpu = claim.get("needs_gpu") is True
    audio_path = work / tjobs.AUDIO
    timeline_path = work / tjobs.TIMELINE
    output_path = str(work / OUTPUT_NAME)

    # Cartoon 3D and mascots render on the GPU only (TMDEV-179, TMDEV-186).
    # The gateway offers such a video only to a renderer whose GPU passed its
    # test; one whose GPU fails it now is re-tested, and if it still fails the
    # video goes back to the queue (gpu_ok false: the gateway stops sending
    # this renderer GPU work, and fails the video if no renderer can take it).
    if needs_gpu and not _render_on_gpu():
        probe = _probe_and_queue("a Cartoon 3D video needs the GPU" if cartoon else "a mascot video needs the GPU")
        if not _render_on_gpu():
            why = (probe.get("error") or "").strip() or "no GPU is configured"
            return {"outcome": "error", "on_gpu": False, "gpu_ok": False, "gpu_probe": probe,
                    "error": f"The renderer hit an error: this video renders on the GPU only, and this "
                             f"renderer's GPU did not pass its test ({why})"}

    render_props = {
        "sceneConfigPath": f"/public/{video_id}/scene-config.json",
        "timelinePath": f"/public/{video_id}/timeline.json",
        "audioPath": f"/public/{video_id}/audio.mp3",
        # From the settings table (through the claim), never from
        # scene-config.json: the agent authors that file, and the watermark
        # must not be the agent's to drop.
        "watermark": settings.get("watermark", True) is not False,
    }
    if (public / MASCOT_CODE).is_file():
        # The version pinned when the scenes were written: the gateway bundles
        # that version's code, never the mascot's current one.
        render_props["mascotPath"] = f"/public/{video_id}/{MASCOT_CODE}"
    props = json.dumps(render_props)
    total_frames = _total_frames(claim, timeline_path)

    log.info(f"[{video_id}] rendering", extra={"video_id": video_id})
    t0 = time.monotonic()
    if cartoon:
        on_gpu = _render_on_gpu()
        gl_argv, gl_env = _gl_args(on_gpu)
        outcome, detail = _render_cartoon(video_id, work, props, output_path, gl_argv, gl_env, timeout_secs,
                                          stall_secs, total_frames, audio_path)
        if job.stopped:
            raise _Stopped()
        if outcome == "ok":
            log.info(f"[{video_id}] render complete ({detail})", extra={"video_id": video_id})
            return _succeeded(job, output_path, on_gpu, total_frames, time.monotonic() - t0)
        if outcome == "hung":
            # environmental, as a timeout of a single render is: requeued
            # rather than bounced to the agent, and a GPU that may have wedged
            # is re-tested
            what = f"Render stalled: {detail}"
            log.error(f"[{video_id}] {what}", extra={"video_id": video_id})
            return _failure("stalled", what, on_gpu, "a Cartoon 3D render on the GPU stalled")
        log.error(f"[{video_id}] render failed: {detail}", extra={"video_id": video_id})
        return _failure("failed", detail, on_gpu, "a Cartoon 3D render on the GPU failed")
    try:
        # start_new_session=True puts npx and everything it spawns (node,
        # Chromium, ffmpeg) in one new process group. subprocess.run's own
        # timeout only kills the direct child it started — any grandchildren
        # (Chromium, ffmpeg) survive, get reparented to this container's PID 1
        # (this same renderer process), and keep running invisibly until they
        # finish on their own, competing with whatever render claims the video
        # next (TMDEV-57, confirmed live: a timed-out render left <defunct>
        # Chromium/ffmpeg processes and an orphaned temp file behind). Using
        # Popen directly so a killpg on the whole group is possible here.
        # Decided once per render: the same answer picks the flags and,
        # on a failure below, whether the GPU is re-tested.
        on_gpu = _render_on_gpu()
        gl_argv, gl_env = _gl_args(on_gpu)
        proc = _spawn(
            [
                "npx", "remotion", "render", "Composition", output_path,
                "--props", props,
                "--browser-executable-path", CHROMIUM_BIN,
                *gl_argv,
            ],
            cwd=str(REMOTION_DIR),
            env={**os.environ, **gl_env},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            start_new_session=True,
        )
        stdout, stderr, outcome = _wait_for_render(proc, timeout_secs, stall_secs)
        if outcome != "exited":
            _kill_group_and_reap(proc)
            raise subprocess.TimeoutExpired(proc.args, stall_secs if outcome == "stall" else timeout_secs)
        result = subprocess.CompletedProcess(proc.args, proc.returncode, stdout, stderr)
    except subprocess.TimeoutExpired as hung:
        if job.stopped:
            raise _Stopped() from None
        stalled = hung.timeout == stall_secs and stall_secs != timeout_secs
        what = (f"Render stalled: no progress for {stall_secs}s" if stalled
                else f"Render timed out after {timeout_secs}s")
        log.error(f"[{video_id}] {what}", extra={"video_id": video_id})
        # A hung Chromium is environmental, not something the agent can fix
        # by revising the scene — the gateway auto-retries it via
        # RENDER_QUEUED rather than bouncing it to the agent as
        # REVISION_REQUESTED. The GPU is re-tested for the same reason as a
        # failed render below: if it hung, the retry should not use it.
        return _failure("stalled" if stalled else "timeout", what, on_gpu, "a render on the GPU timed out")
    if job.stopped:
        raise _Stopped()

    if result.returncode == 0:
        log.info(f"[{video_id}] render complete", extra={"video_id": video_id})
        return _succeeded(job, output_path, on_gpu, total_frames, time.monotonic() - t0)
    error_msg = result.stderr or result.stdout
    log.error(f"[{video_id}] render failed: {error_msg}", extra={"video_id": video_id})
    return _failure("failed", error_msg, on_gpu, "a render on the GPU failed")


def _succeeded(job: _Job, output_path: str, on_gpu: bool, frames: int, seconds: float) -> dict:
    out = Path(output_path)
    if not out.is_file() or out.stat().st_size == 0:
        return {"outcome": "error", "on_gpu": on_gpu, "gpu_ok": None,
                "error": "The renderer hit an error: Remotion exited cleanly but wrote no video"}
    _upload(job, out)
    return {"outcome": "success", "error": "", "on_gpu": on_gpu, "gpu_ok": None,
            "frames": frames, "seconds": round(max(seconds, 0.001), 3)}


def _upload(job: _Job, out: Path) -> None:
    """PUT the mp4, streamed from disk, while the lease holds (a 403, or a
    409 claim_lost, means the claim was lost: another claim took the video
    over). A failed attempt (a network error, any other answer) is tried
    again, at most UPLOAD_ATTEMPTS times in all. A 409 upload_in_progress (an
    earlier attempt of this claim is still being received) and a 503 busy
    (the gateway's upload slots are full) are not failures but the gateway
    asking to wait: they are tried again after the Retry-After it asks for,
    for as long as UPLOAD_WAIT_SECS, while the claim holds (the heartbeat
    keeps its lease alive, and a heartbeat's stop ends the wait). Other
    renders' uploads over home links can hold every slot for many minutes,
    and a finished render is worth waiting for. A 413 (over the gateway's
    size limit) and a 507 (the main machine is short of disk space) are not
    tried again: the render is reported as an error."""
    last = None
    failures = 0
    waited_since = None
    while True:
        if job.stopped:
            raise _Stopped()
        pause = RETRY_PAUSE_SECS * (failures + 1)
        try:
            with open(out, "rb") as fh:
                resp = _client.send("PUT", _job_path(job.video_id, "output"), content=fh,
                                    headers=_job_headers(job))
        except GatewayError as e:
            last = str(e)
        else:
            if resp.status_code == 200:
                log.info(f"[{job.video_id}] uploaded {out.stat().st_size} bytes", extra={"video_id": job.video_id})
                return
            if resp.status_code == 403:
                raise _LeaseLost("the gateway refused the upload: this renderer does not hold the video any more")
            code = _error_code(resp)
            if resp.status_code == 409 and code == "claim_lost":
                raise _LeaseLost("the gateway discarded the upload: the claim was lost while it was sent")
            if resp.status_code == 413:
                # never smaller on a second try: reported as this render's error
                raise GatewayError(f"the rendered video ({out.stat().st_size} bytes) is larger than the "
                                   "gateway accepts (TUBEMATIC_MAX_OUTPUT_BYTES on the main machine)", 413, code)
            if resp.status_code == 507:
                raise GatewayError("the rendered video could not be uploaded: the main machine is short of disk "
                                   "space for it (insufficient_storage; it keeps TUBEMATIC_MIN_FREE_BYTES free)",
                                   507, code)
            if (resp.status_code, code) in ((409, "upload_in_progress"), (503, "busy")):
                now = _monotonic()
                waited_since = now if waited_since is None else waited_since
                if now - waited_since >= UPLOAD_WAIT_SECS:
                    raise GatewayError(f"the rendered video could not be uploaded: the gateway stayed busy "
                                       f"({code}) for {UPLOAD_WAIT_SECS}s")
                wait = max(RETRY_PAUSE_SECS, min(_retry_after(resp), MAX_RETRY_AFTER_SECS))
                log.info(f"[{job.video_id}] the gateway cannot take the upload yet ({code}); "
                         f"trying again in {wait:g}s", extra={"video_id": job.video_id})
                time.sleep(wait)
                continue
            last = f"the upload answered {resp.status_code} {code}".strip()
        failures += 1
        log.warning(f"[{job.video_id}] upload attempt {failures}/{UPLOAD_ATTEMPTS} failed: {last}",
                    extra={"video_id": job.video_id})
        if failures >= UPLOAD_ATTEMPTS:
            raise GatewayError(f"the rendered video could not be uploaded: {last}")
        time.sleep(pause)


def _retry_after(resp: httpx.Response) -> float:
    try:
        return max(0.0, float(resp.headers.get("Retry-After", "")))
    except ValueError:
        return 0.0


def _post_result(job: _Job, body: dict) -> bool:
    """Report how the render ended. Retried a few times; a result that cannot
    be delivered is left to the lease, whose expiry re-queues the video. The
    error is cut to RESULT_ERROR_CHARS (Remotion's stderr is unbounded) so the
    body stays under the gateway's JSON limit; the comment it becomes keeps
    far fewer characters than that anyway."""
    vid = job.video_id
    if isinstance(body.get("error"), str) and len(body["error"]) > RESULT_ERROR_CHARS:
        body = {**body, "error": body["error"][:RESULT_ERROR_CHARS]}
    for attempt in range(1, RESULT_ATTEMPTS + 1):
        try:
            resp = _client.send("POST", _job_path(vid, "result"), json_body=body, headers=_job_headers(job))
        except GatewayError as e:
            log.warning(f"[{vid}] reporting the result failed (attempt {attempt}/{RESULT_ATTEMPTS}): {e}",
                        extra={"video_id": vid})
        else:
            if resp.status_code == 200:
                log.info(f"[{vid}] reported {body.get('outcome')}", extra={"video_id": vid})
                return True
            if resp.status_code in (400, 403):
                _note_error(f"[{vid}] the gateway dropped the result ({resp.status_code} {_error_code(resp)})")
                return False
            log.warning(f"[{vid}] the result answered {resp.status_code} (attempt {attempt}/{RESULT_ATTEMPTS})",
                        extra={"video_id": vid})
        if attempt < RESULT_ATTEMPTS:
            time.sleep(RETRY_PAUSE_SECS * attempt)
    _note_error(f"[{vid}] the result could not be reported; the lease will expire and the video be re-queued")
    return False


def _run_job(claim: dict) -> None:
    """One claimed video, with a boundary: whatever escapes the download, the
    staging or the render (an OSError from a disk or an executable, a bug) is
    this video's error, reported and retried as a stall is, never the
    renderer's exit. A stopped render or a lost lease is thrown away with no
    result. The job directory, the staged public files and (remote) the staged
    scenes are removed however it ended."""
    vid = claim.get("video_id")
    claim_id = claim.get("claim_id")
    if not isinstance(vid, str) or not vid or not isinstance(claim_id, str) or not claim_id:
        # Nothing could be fetched or reported for it; its lease runs out and
        # the video is re-queued.
        _note_error("the gateway handed out a claim with no video id or no claim id")
        return
    job = _Job(vid, claim_id)
    with _st.lock:
        _st.job = job
    work = public = None
    body = None
    try:
        work = tjobs.job_dir(RENDER_TMP, vid)
        public = tjobs.join_below(REMOTION_DIR / "public", vid)
        _clean_job(work, public)
        work.mkdir(parents=True)
        log.info(f"[{vid}] claimed ({claim.get('kind')})", extra={"video_id": vid})
        _download_bundle(job, work)
        _stage(job, work, public)
        body = _render(job, claim, work, public)
    except _Stopped:
        log.warning(f"[{vid}] render stopped by the gateway; discarded", extra={"video_id": vid})
    except _LeaseLost as e:
        _note_error(f"[{vid}] {e}; the render is discarded")
    except _BundleUnavailable as e:
        _note_error(f"[{vid}] the gateway cannot bundle the job's files: {e}")
        body = {"outcome": "error", "on_gpu": False, "gpu_ok": None,
                "error": f"The renderer hit an error: the job's files could not be fetched: {e}"}
    except Exception as exc:  # noqa: BLE001 — the boundary itself
        if not job.stopped:
            log.exception(f"[{vid}] the render raised: {exc}", extra={"video_id": vid})
            _note_error(f"[{vid}] the render raised: {exc}")
            body = {"outcome": "error", "on_gpu": False, "gpu_ok": None,
                    "error": f"The renderer hit an error: {exc}"}
    finally:
        _clean_job(work, public)
    try:
        if body is not None and not job.stopped:
            _post_result(job, body)
        elif job.stopped:
            log.warning(f"[{vid}] render stopped by the gateway; no result sent", extra={"video_id": vid})
    finally:
        with _st.lock:
            _st.job = None


# ── The loop ──────────────────────────────────────────────────────────────────

def _loop_once() -> float:
    """One pass: a requested probe (only ever between renders), the stills
    server, then a claim and its render. Returns how long to wait before the
    next pass."""
    with _st.lock:
        probe_now, _st.probe_now = _st.probe_now, False
    if probe_now:
        _probe_and_queue("requested from the dashboard")
        _beat()     # the answer now, not a heartbeat later
    if _is_builtin():
        _ensure_stills_server()
    with _st.lock:
        ready = not _st.started and _st.enabled and not _st.needs_upgrade
    if not ready:
        return POLL_INTERVAL_SECS
    try:
        resp = _client.send("POST", "/v1/claim", json_body={})
    except GatewayError as e:
        _note_error(f"claim failed: {e}")
        return NETWORK_RETRY_SECS
    if resp.status_code in (200, 204):
        with _st.lock:
            _st.last_error = ""
    if resp.status_code == 204:
        return POLL_INTERVAL_SECS
    if resp.status_code == 409:
        code = _error_code(resp)
        with _st.lock:
            if code == "needs_upgrade":
                _st.needs_upgrade = True
            elif code == "disabled":
                _st.enabled = False
        log.warning("claim refused: this renderer needs upgrade" if code == "needs_upgrade"
                    else f"claim refused: {code or resp.status_code}")
        return POLL_INTERVAL_SECS
    if resp.status_code == 401 and _error_code(resp) == "credential_expired":
        _note_error(CREDENTIAL_EXPIRED_MESSAGE)
        return NETWORK_RETRY_SECS
    if resp.status_code != 200:
        _note_error(f"claim answered {resp.status_code} {_error_code(resp)}".strip())
        return NETWORK_RETRY_SECS
    try:
        claim = resp.json()
    except ValueError:
        claim = None
    if not isinstance(claim, dict):
        _note_error("claim answered 200 with no JSON body")
        return NETWORK_RETRY_SECS
    _run_job(claim)
    return 0


# The renderer reads no settings, so its JSONL log keeps the
# log_retention_days setting's default (each service prunes its own files;
# keep in sync with pipeline.py SETTINGS_SPEC), and redaction covers the one
# credential this process holds — the built-in token or the enrolled
# credential — on top of tlog's header- and URL-shaped patterns. The stored
# API keys never reach a renderer, so there is nothing else of theirs to hide.
LOG_RETENTION_DAYS = 14


def _log_secrets() -> list:
    """Called from inside the log formatter: must not log and must not raise."""
    try:
        if _client is not None:
            credential = _client.identity.credential()
        elif _is_builtin():
            credential = tauth.read_secret(BUILTIN_TOKEN_NAME)
        else:
            credential = (_load_state(_state_file()) or {}).get("credential") or ""
        return [credential] if credential else []
    except Exception:  # noqa: BLE001 — see docstring
        return []


def main() -> None:
    global _client
    # Mirrors entrypoint.sh's umask — keeps the log files the renderer writes
    # into the bind-mounted /logs host-deletable. The state file is created
    # with an explicit 0600, which a umask of 0 leaves exactly as it is.
    os.umask(0)
    # Adds a JSONL file handler *alongside* the stdout one configured above —
    # `docker compose logs tubematic-renderer` has to keep working unchanged.
    # A missing or unwritable /logs leaves this a no-op.
    tlog.setup_json_logging("renderer", LOG_DIR, retention_days=LOG_RETENTION_DAYS, secrets=_log_secrets)
    log.info(f"renderer starting ({'built-in' if _is_builtin() else 'remote'}, version {current_version()})")
    _st.compute = _compute_report()
    # Whatever a previous run of this process left (it was killed mid-job) is
    # nobody's now: the gateway re-queues that video when the first heartbeat
    # says `started`.
    shutil.rmtree(RENDER_TMP, ignore_errors=True)
    try:
        _clear_generated()
    except Exception as e:  # noqa: BLE001
        log.error(f"could not clear the staged scenes: {e}")
    while _client is None:
        try:
            _client = GatewayClient(_load_identity(_st.compute))
        except (EnrollmentError, GatewayError) as e:
            log.error(f"the renderer cannot start: {e}. Trying again in {ENROLL_RETRY_SECS}s")
            time.sleep(ENROLL_RETRY_SECS)
    # Before the first claim, so no render ever runs on an unverified GPU,
    # and every start (which is when a GPU change applies) sends a fresh
    # answer for the dashboard with the first heartbeat.
    _probe_and_queue("the renderer started")
    if _is_builtin():
        _ensure_stills_server()
    # The first heartbeat says `started`, and the gateway re-queues whatever
    # this renderer held before it restarted, before this one claims anything.
    while not _beat():
        time.sleep(NETWORK_RETRY_SECS)
    _start_heartbeat_thread()
    while True:
        try:
            wait = _loop_once()
        except Exception as exc:  # noqa: BLE001 — the renderer must outlive any one pass
            log.exception("render loop pass failed")
            _note_error(f"render loop pass failed: {exc}")
            wait = NETWORK_RETRY_SECS
        if wait:
            time.sleep(wait)


if __name__ == "__main__":
    main()
