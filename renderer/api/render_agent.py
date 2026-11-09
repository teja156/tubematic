#!/usr/bin/env python3
"""Tubematic render agent: the tubematic-renderer container's only job.

Polls the shared SQLite DB for videos in RENDER_QUEUED status, atomically
claims one, renders it via Remotion, and runs the AI-review/failure tail.
Making videos.status the durable queue means a restart can't lose a queued or
in-flight job — see _reconcile_rendering_videos.

Everything else the old single worker loop did (publishing, Auto Pilot,
metrics, price sync, retention, notifications, the stalled-voicing sweep) runs
in tubematic-worker (worker.py), so a render that holds this loop for an hour
never delays a publish, an approval or a notification, and recreating this
container (onboard.py --step gpu does) never interrupts them either.

Run: python3 render_agent.py
"""
import json
import re
import threading
import logging
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

import ai_review
import db
import pipeline
from tubematic_core import jobfiles as tjobs
from tubematic_core import logging as tlog
from tubematic_core import usage as tusage

DB_PATH = os.getenv("TUBEMATIC_DB", "/data/tubematic.db")
OUTPUT_DIR = Path(os.getenv("OUTPUT_BASE_PATH", "/output_videos"))
REMOTION_DIR = Path("/app/remotion")
JOBS_DIR = os.getenv("TUBEMATIC_JOBS_DIR", "/jobs")   # the volume the stills server serves as /public/
LOG_DIR = Path(os.getenv("TUBEMATIC_LOG_DIR", "/logs"))
CHROMIUM_BIN = os.getenv("CHROMIUM_BIN", "/usr/bin/chromium")

POLL_INTERVAL_SECS = int(os.getenv("RENDER_POLL_INTERVAL_SECS", "20"))
# render_timeout_secs is a live pipeline setting (TMDEV-57), not a fixed
# constant — read via _render_timeout_secs() at the point of use so it can be
# changed via onboard/dashboard without a renderer restart.

# gemini_feedback is stored WHOLE — no cap. The review prompt no longer limits
# the number of must-fix entries or their length, so any cap here would silently
# drop real blocking defects, and this column is what the agent actually acts on
# (get_video returns it in full). One row per video, overwritten each round, so
# unbounded length costs nothing that matters.
#
# The comment thread keeps its cap: it is append-only, and it is a pointer to the
# review rather than the review itself. _format_feedback orders
# Overall -> Must fix -> Suggestions, so a truncated comment loses suggestions
# first and always keeps the blocking items, and _truncate_comment appends an
# explicit marker naming gemini_feedback as the full copy.
_COMMENT_MAX_CHARS = 2000
_COMMENT_TRUNCATION_NOTE = (
    "\n\n… truncated — read `gemini_feedback` on this video for the complete review."
)


def _truncate_comment(text: str) -> str:
    """Cap a comment, saying so when it bites.

    Silent truncation is the failure mode worth avoiding: the agent cannot tell
    a short review from a clipped one, and since must-fix entries are now
    unbounded a clipped comment can hide blocking defects entirely.
    """
    text = text or ""
    if len(text) <= _COMMENT_MAX_CHARS:
        return text
    keep = _COMMENT_MAX_CHARS - len(_COMMENT_TRUNCATION_NOTE)
    return text[:keep].rstrip() + _COMMENT_TRUNCATION_NOTE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [renderer] %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S%z",
    stream=sys.stdout,
)
log = logging.getLogger("render_agent")



def _setting(key: str, default: str) -> str:
    """Read a runtime setting from the settings table; fall back to env then default.

    The settings table is the live source of truth; env is a fallback only,
    never written by onboarding.

    A **blank** row falls through rather than winning, which matters since
    TMDEV-73: onboarding seeds "" for every credential it did not ask about, so
    an existing-but-empty row would otherwise shadow a key supplied through the
    container environment — silently skipping AI review on a stack that has one.
    Matches mcp/server.py's key helpers and pipeline.py's _secret, which both
    use `stored or env`. No caller wants a blank: the ints would raise on
    int(""), and the model/bool keys have no meaningful empty value.
    """
    try:
        with db.conn(DB_PATH) as con:
            row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        if row is not None and row["value"] != "":
            return row["value"]
    except Exception:
        pass
    return os.getenv(key.upper(), default)


def _max_render_retries() -> int:
    try:
        return int(_setting("max_render_retries", "1"))
    except (ValueError, TypeError):
        return 1


def _max_ai_review_loops() -> int:
    """How many AI reviews a video gets before one is force-accepted.

    Split out from the render-retry cap by VQA-7. The two budgets used to be one
    knob, so lowering the review loop — which VQA-7 wanted, since a review
    round can now cost a paid re-voice and its findings were often cosmetic —
    would have halved the render crash/timeout retry budget as a side effect.
    Those failures are unrelated, and TMDEV-57 showed a large video
    legitimately needing a second render attempt after a timeout.
    """
    try:
        return int(_setting("ai_review_max_loops", "1"))
    except (ValueError, TypeError):
        return 1


def _render_timeout_secs() -> int:
    """The absolute ceiling on one render. Keep the default in sync with
    pipeline.py SETTINGS_SPEC."""
    try:
        return int(_setting("render_timeout_secs", "10800"))
    except (ValueError, TypeError):
        return 10800


def _render_stall_timeout_secs() -> int:
    """How long Remotion's progress counter may stand still before the render
    is judged hung. Keep the default in sync with pipeline.py SETTINGS_SPEC."""
    try:
        return int(_setting("render_stall_timeout_secs", "600"))
    except (ValueError, TypeError):
        return 600


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
    see progress. The full output is kept: _handle_render_failure records it.
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


def _scene_config_is_cartoon3d(scene_config_path) -> bool:
    """Whether the written scene-config renders a Cartoon 3D world: one
    generated scene whose props carry `cartoon3d` (the beats). Keep the key
    in sync with mcp/cartoon.py's CARTOON_PROPS."""
    try:
        config = json.loads(Path(scene_config_path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    scenes = config.get("scenes") if isinstance(config, dict) else None
    return isinstance(scenes, list) and any(
        isinstance(s, dict) and isinstance(s.get("props"), dict) and isinstance(s["props"].get("cartoon3d"), dict)
        for s in scenes)


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
CARTOON_CHUNK_FRAMES = 450          # 15 s at 30 fps
CARTOON_CHUNK_ATTEMPTS = 2          # a segment that hangs or fails is tried once more, fresh
CARTOON_MIX = ("cartoon", "audio", "mix", "mix.wav")
CARTOON_SOURCE = ("cartoon", "source.json")          # what submit_render froze: mcp/cartoon.py's SOURCE_RECORD
GENERATED_DIR = REMOTION_DIR / "src" / "scenes" / "generated"   # keep in sync with mcp/cartoon.py's mix_file
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


def _soundtrack_for(video_id: str, voice_path: Path) -> Path:
    """The audio to mux: the synthesised mix when it exists and is at least as
    new as the voice (a re-voiced video makes an older mix stale), else the voice."""
    try:
        # join_below refuses a symlink in any component on the way
        mix = tjobs.join_below(tjobs.job_dir(pipeline.JOBS_DIR, video_id), *CARTOON_MIX)
        if mix.is_file() and not mix.is_symlink() and mix.stat().st_mtime >= voice_path.stat().st_mtime:
            return mix
    except (OSError, tjobs.UnsafePath):
        pass
    return voice_path


def _cartoon_source_error(video_id: str) -> str | None:
    """Why the video's generated source is not the tree submit_render froze
    (its fingerprint under the job, written when the beat gate had passed):
    it was edited since, a non-regular file sits in it, or there is no record
    at all (only submit_render queues a Cartoon 3D video, and it always
    writes one: a missing or replaced record is not rendered). None when the
    live tree is the frozen one."""
    try:
        # join_below refuses a symlink in any component on the way (a planted
        # `cartoon` link would redirect the record itself)
        record = tjobs.join_below(tjobs.job_dir(pipeline.JOBS_DIR, video_id), *CARTOON_SOURCE)
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


def _render_cartoon(video_id: str, props: str, output_path: str, gl_argv: list, gl_env: dict,
                    timeout_secs: int, stall_secs: int, total_frames: int, voice_path: Path) -> tuple:
    """Render a Cartoon 3D video in segments and mux its soundtrack. Returns
    (outcome, detail): outcome "ok", "hung" (a segment stalled, or the whole
    render ran past timeout_secs: environmental, retried by the caller as a
    timeout is) or "failed" (Remotion or ffmpeg reported an error, the source
    is not the one that was queued, or the render could not be run at all).
    timeout_secs caps the whole render, every segment and retry included,
    as it caps an ordinary render."""
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
            err = _cartoon_source_error(video_id)
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
                proc = subprocess.Popen(
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
        err = _cartoon_source_error(video_id)
        if err:
            return "failed", err
        # ffmpeg spends what is left of the same deadline, FFMPEG_TIMEOUT_SECS at most
        remaining = deadline - _clock()
        if remaining <= 0:
            return "hung", f"joining the segments: the render ran past {timeout_secs}s in all"
        list_file = work / "segments.txt"
        list_file.write_text("".join(f"file '{p.name}'\n" for p in segments), encoding="utf-8")
        silent = work / "video.mp4"
        joined = subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file),
                                 "-c", "copy", str(silent)], cwd=str(work), capture_output=True, text=True,
                                timeout=min(FFMPEG_TIMEOUT_SECS, remaining))
        if joined.returncode != 0 or not silent.is_file():
            return "failed", f"joining the {len(segments)} segments failed: {(joined.stderr or joined.stdout).strip()[-800:]}"
        remaining = deadline - _clock()
        if remaining <= 0:
            return "hung", f"muxing the soundtrack: the render ran past {timeout_secs}s in all"
        audio = _soundtrack_for(video_id, voice_path)
        muxed = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(silent), "-i", str(audio),
                                "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                                "-shortest", "-movflags", "+faststart", str(tmp_out)],
                               capture_output=True, text=True, timeout=min(FFMPEG_TIMEOUT_SECS, remaining))
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

GPU_PROBE_RESULT_KEY = pipeline.GPU_PROBE_RESULT_KEY
GPU_PROBE_REQUEST_KEY = pipeline.GPU_PROBE_REQUEST_KEY
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
    both run `npx remotion` (npx → node → Chromium → ffmpeg)."""
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
    string, store the result for the dashboard, and set _gpu_verified.

    Runs even with no GPU configured: then it uses the CPU flags, and the
    stored software renderer string is what the dashboard's Test button
    shows. Never raises — the render loop must survive a broken probe."""
    global _gpu_verified
    cfg = _gpu_config()
    configured = bool(cfg["uuid"])
    started = pipeline.now_precise()
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
    try:
        with db.conn(DB_PATH) as con:
            con.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?)"
                " ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (GPU_PROBE_RESULT_KEY, json.dumps(result)))
    except Exception:
        log.exception("could not store the GPU probe result")
    return result


def _gpu_probe_requested() -> bool:
    """A dashboard Test request newer than the last probe's start."""
    requested = _setting(GPU_PROBE_REQUEST_KEY, "")
    if not requested:
        return False
    try:
        last = json.loads(_setting(GPU_PROBE_RESULT_KEY, "") or "{}").get("at", "")
    except (ValueError, AttributeError):
        last = ""
    return requested > (last or "")


def _sweep_gpu_probe() -> None:
    """Run a requested probe. One pass of the render loop, so a request waits
    behind a render in progress — the API reports that as queued."""
    try:
        if _gpu_probe_requested():
            _run_gpu_probe(reason="requested from the dashboard")
    except Exception:
        log.exception("GPU probe sweep failed")


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


def _reconcile_rendering_videos() -> None:
    """On startup, requeue (or fail) any video stuck in RENDERING.

    These are videos whose render was interrupted by a renderer crash/restart.
    Mirrors the normal render-crash backstop (_handle_render_failure): each
    reconciliation atomically increments render_fail_count and escalates
    straight to FAILED once it exceeds max_render_retries, instead of
    unconditionally retrying forever — otherwise a render that reliably
    crashes the renderer (e.g. OOM) loops RENDERING -> restart -> RENDER_QUEUED
    -> RENDERING forever and never reaches the FAILED backstop.

    Requeues to RENDER_QUEUED (not REVISION_REQUESTED) so the renderer retries
    automatically without needing the agent — an improvement over the old
    in-Flask design, where a restart always bounced the video back to the
    agent even though nothing about the render itself was wrong.
    """
    try:
        with db.conn(DB_PATH) as con:
            rows = con.execute("SELECT id FROM videos WHERE status = 'RENDERING'").fetchall()
    except Exception as e:
        log.error(f"startup reconcile check failed: {e}")
        return

    if not rows:
        return

    max_retries = _max_render_retries()
    for row in rows:
        video_id = row["id"]
        try:
            with db.conn(DB_PATH) as con:
                con.execute(
                    "UPDATE videos SET render_fail_count = render_fail_count + 1, updated_at = ? WHERE id = ?",
                    (db._now(), video_id),
                )
                count_row = con.execute(
                    "SELECT render_fail_count FROM videos WHERE id = ?", (video_id,)
                ).fetchone()
                fail_count = count_row["render_fail_count"] if count_row else 1

            if fail_count > max_retries:
                db.add_comment(DB_PATH, video_id, "agent",
                                f"Render interrupted by renderer restart {fail_count} times "
                                f"(limit {max_retries}) — giving up.")
                db.set_status(DB_PATH, video_id, "FAILED", only_if="RENDERING")
            else:
                db.add_comment(DB_PATH, video_id, "agent",
                                "Render interrupted by renderer restart — automatically re-queued.")
                db.set_status(DB_PATH, video_id, "RENDER_QUEUED", only_if="RENDERING")
        except Exception as exc:
            log.error(f"failed to reconcile video {video_id}: {exc}", extra={"video_id": video_id})

    log.info(f"startup: reconciled {len(rows)} interrupted RENDERING video(s)")


def _claim_next() -> str | None:
    """Atomically claim the oldest RENDER_QUEUED video. Returns its id, or None if idle."""
    try:
        with db.conn(DB_PATH) as con:
            row = con.execute(
                "SELECT id FROM videos WHERE status = 'RENDER_QUEUED' ORDER BY updated_at ASC, id ASC LIMIT 1"
            ).fetchone()
    except Exception as e:
        log.error(f"claim query failed: {e}")
        return None
    if not row:
        return None
    video_id = row["id"]
    # Guarded in the UPDATE's own WHERE clause (not SELECT-then-compare) —
    # the same atomic-claim pattern used throughout the pipeline. With a
    # single renderer process this never actually loses a race, but it's the
    # same defensive shape as submit_render's claim. The hold is in the same
    # statement for the same reason: onboarding writes it, then looks for a
    # RENDERING row, and SQLite's single writer means a claim either landed
    # before the hold (and is seen) or sees the hold (and does not happen).
    now = db._now()
    try:
        with db.conn(DB_PATH) as con:
            cur = con.execute(
                "UPDATE videos SET status = 'RENDERING', updated_at = ? "
                "WHERE id = ? AND status = 'RENDER_QUEUED' AND NOT EXISTS ("
                " SELECT 1 FROM settings WHERE key = ? AND value > ?)",
                (now, video_id, pipeline.RENDER_CLAIM_HOLD_KEY, now))
    except Exception as e:
        log.error(f"claim failed: {e}")
        return None
    return video_id if cur.rowcount > 0 else None


def _stage_and_render(video_id: str) -> None:
    """Render one already-claimed (status=RENDERING) video: stage its job
    files into the Remotion public dir, invoke Remotion, then run the tail."""
    with db.conn(DB_PATH) as con:
        row = con.execute(
            "SELECT project_id, voice_file_path, timeline_path, scene_config_path, "
            "visual_style, resolved_renderer FROM videos WHERE id = ?",
            (video_id,),
        ).fetchone()
    if not row:
        log.error(f"[{video_id}] video row disappeared after claim — skipping", extra={"video_id": video_id})
        return

    # Every location is derived from the ids, never read from the row's path
    # columns (TMDEV-162): those were once writable through PATCH and
    # update_video, so a row tampered with before the fix could name any file
    # the renderer can read, and it would be staged into the render. The columns
    # still say whether each file was written.
    try:
        audio_path = tjobs.job_file(pipeline.JOBS_DIR, video_id, tjobs.AUDIO)
        timeline_path = tjobs.job_file(pipeline.JOBS_DIR, video_id, tjobs.TIMELINE)
        scene_config_path = tjobs.job_file(pipeline.JOBS_DIR, video_id, tjobs.SCENE_CONFIG)
        images_dir = tjobs.images_dir(pipeline.JOBS_DIR, video_id)
        output_file = tjobs.output_file(OUTPUT_DIR, row["project_id"], video_id)
    except tjobs.UnsafePath as e:
        # Not something a revision can fix, and retrying renders the same
        # refusal, so it goes straight to FAILED for a human to look at.
        log.error(f"[{video_id}] refusing to render: {e}", extra={"video_id": video_id})
        db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
            f"Render refused, moved to FAILED: {e}. The video's id or its project's id "
            "cannot be used as a file path, so nothing was staged or rendered."))
        db.set_status(DB_PATH, video_id, "FAILED", only_if="RENDERING")
        return

    missing = [
        name for name, written, p in [
            ("voice_file_path", row["voice_file_path"], audio_path),
            ("timeline_path", row["timeline_path"], timeline_path),
            ("scene_config_path", row["scene_config_path"], scene_config_path),
        ] if not written or not p.is_file()
    ]
    if missing:
        db.add_comment(DB_PATH, video_id, "agent", f"Render failed: missing job file(s): {missing}")
        db.set_status(DB_PATH, video_id, "REVISION_REQUESTED", only_if="RENDERING")
        return

    public_dir = REMOTION_DIR / "public" / video_id
    public_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(scene_config_path, public_dir / tjobs.SCENE_CONFIG)
    shutil.copy(timeline_path, public_dir / tjobs.TIMELINE)
    shutil.copy(audio_path, public_dir / tjobs.AUDIO)

    # Per-video generated images (TMDEV-29). Optional — most videos have none,
    # so this must stay out of the `missing` precondition list above. Scenes
    # reference these as /public/<video_id>/images/<name>, which is exactly what
    # staticFile() would resolve to; validate_job checks they exist first.
    # Symlinks are skipped: copytree follows them, so a planted link would copy
    # whatever it points at into the render.
    if images_dir.is_dir():
        shutil.copytree(images_dir, public_dir / tjobs.IMAGES, dirs_exist_ok=True,
                        ignore=tjobs.ignore_symlinks)

    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_path = str(output_file)

    props = json.dumps({
        "sceneConfigPath": f"/public/{video_id}/scene-config.json",
        "timelinePath": f"/public/{video_id}/timeline.json",
        "audioPath": f"/public/{video_id}/audio.mp3",
        # From the settings table, never from scene-config.json: the agent
        # authors that file, and the watermark must not be the agent's to drop.
        "watermark": _setting("watermark_enabled", "true").lower() == "true",
    })

    timeout_secs = _render_timeout_secs()
    stall_secs = _render_stall_timeout_secs()

    # Cartoon 3D renders on the GPU only (TMDEV-179): policy, decided where the
    # style is chosen, and enforced here for a video approved before its GPU
    # went away. Never judged on an unprobed GPU: the renderer probes after
    # every start, so a video claimed first simply triggers that probe. No
    # CPU fallback and no retry: straight to FAILED, bypassing the render
    # retry counter, since neither a requeue nor the agent can bring a GPU
    # back, and the comment is the only thing the human gets.
    cartoon = (_scene_config_is_cartoon3d(scene_config_path)
               or (row["visual_style"] or "") == "cartoon_3d"
               or (row["resolved_renderer"] or "") == "cartoon_3d")
    if cartoon and not _render_on_gpu():
        if pipeline.gpu_probe_status(_setting("gpu_probe_result", "")) == "unknown":
            _run_gpu_probe(reason="a Cartoon 3D video needs the GPU")
    if cartoon and not _render_on_gpu():
        probe = json.loads(_setting("gpu_probe_result", "") or "null") or {}
        status = pipeline.gpu_probe_status(_setting("gpu_probe_result", ""))
        why = (probe.get("error") or "").strip() if isinstance(probe, dict) else ""
        db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
            f"Not rendered, moved to FAILED: this video is Cartoon 3D, which renders on the GPU "
            f"only, and the renderer's GPU is {status}" + (f" — {why}" if why else "") +
            ". Configure or fix the GPU (python onboard.py --step gpu; Test GPU on the dashboard "
            "Settings page), then create the video again."))
        db.set_status(DB_PATH, video_id, "FAILED", only_if="RENDERING")
        return

    log.info(f"[{video_id}] rendering -> {output_path}", extra={"video_id": video_id})
    if cartoon:
        on_gpu = _render_on_gpu()
        gl_argv, gl_env = _gl_args(on_gpu)
        try:
            total_frames = int(json.loads(timeline_path.read_text(encoding="utf-8")).get("totalFrames", 0))
        except (OSError, ValueError, TypeError, AttributeError):
            total_frames = 0
        outcome, detail = _render_cartoon(video_id, props, output_path, gl_argv, gl_env, timeout_secs, stall_secs,
                                          total_frames, audio_path)
        if outcome == "ok":
            log.info(f"[{video_id}] render complete ({detail}) -> {output_path}", extra={"video_id": video_id})
            _handle_render_success(video_id, output_path)
            return
        if outcome == "hung":
            # environmental, as a timeout of a single render is: requeue rather
            # than bounce to the agent, and re-test a GPU that may have wedged
            what = f"Render stalled: {detail}"
            log.error(f"[{video_id}] {what}", extra={"video_id": video_id})
            _handle_render_failure(video_id, what, retry_status="RENDER_QUEUED")
        else:
            log.error(f"[{video_id}] render failed: {detail}", extra={"video_id": video_id})
            _handle_render_failure(video_id, detail)
        if on_gpu:
            _run_gpu_probe(reason="a Cartoon 3D render on the GPU " + ("stalled" if outcome == "hung" else "failed"))
        return
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
        proc = subprocess.Popen(
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
        stalled = hung.timeout == stall_secs and stall_secs != timeout_secs
        what = (f"Render stalled: no progress for {stall_secs}s" if stalled
                else f"Render timed out after {timeout_secs}s")
        log.error(f"[{video_id}] {what}", extra={"video_id": video_id})
        # A hung Chromium is environmental, not something the agent can fix
        # by revising the scene — auto-retry via RENDER_QUEUED (same terminal
        # choice as the crash-reconcile path above) rather than bouncing to
        # the agent as REVISION_REQUESTED.
        _handle_render_failure(video_id, what, retry_status="RENDER_QUEUED")
        if on_gpu:
            # Same reason as a failed render below: if the GPU hung, the retry
            # this just queued should run on the CPU.
            _run_gpu_probe(reason="a render on the GPU timed out")
        return

    if result.returncode == 0:
        log.info(f"[{video_id}] render complete -> {output_path}", extra={"video_id": video_id})
        _handle_render_success(video_id, output_path)
    else:
        error_msg = result.stderr or result.stdout
        log.error(f"[{video_id}] render failed: {error_msg}", extra={"video_id": video_id})
        _handle_render_failure(video_id, error_msg)
        if on_gpu:
            # A GPU that stopped working (a driver update, a reset) fails every
            # render after it. Re-testing now means the next one falls back to
            # the CPU instead of failing the same way.
            _run_gpu_probe(reason="a render on the GPU failed")


def _handle_render_success(video_id: str, output_path: str) -> None:
    try:
        db.update_fields(DB_PATH, video_id, video_path=output_path)

        # Keep the "false" in sync with pipeline.py SETTINGS_SPEC (TMDEV-165).
        gemini_review_enabled = _setting("gemini_review_enabled", "false").lower() == "true"
        gemini_api_key = _setting("gemini_api_key", "")

        if not gemini_review_enabled or not gemini_api_key:
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
            return

        max_review_loops = _max_ai_review_loops()

        # Atomically increment ai_review_count
        with db.conn(DB_PATH) as con:
            con.execute(
                "UPDATE videos SET ai_review_count = ai_review_count + 1, updated_at = ? WHERE id = ?",
                (db._now(), video_id),
            )
            row = con.execute(
                "SELECT ai_review_count, script, tts_text, visual_style, "
                "resolved_visual_style, resolved_renderer FROM videos WHERE id = ?", (video_id,)
            ).fetchone()
            new_count = row["ai_review_count"] if row else 1
            # VQA-6: the review's pronunciation reference. script is the
            # authored wording the captions show; tts_text is what was
            # actually sent to ElevenLabs (empty on rows voiced before that
            # column existed — the review degrades to the script alone).
            script_text = (row["script"] if row else "") or ""
            tts_text = (row["tts_text"] if row else "") or ""
            # TMDEV-101: the canvas the video was deliberately painted on, and
            # whether it may contain figures, so the reviewer judges it against
            # its own intended look. The two are independent — an "auto" video
            # can be dark AND full of held, discretely-posed figures — so they
            # are passed separately rather than as one register name. A blank
            # canvas means "auto" never settled, which the prompt handles by
            # stating no contract at all rather than assuming one.
            raw_style = (row["visual_style"] if row else "") or ""
            canvas = pipeline.effective_canvas(
                raw_style, (row["resolved_visual_style"] if row else "") or "")
            has_figures = pipeline.figures_allowed(raw_style)
            # Narrower than has_figures: "illustrated" has figures but they are
            # generated artwork, so the reviewer must not be told that simple
            # line art is intended there.
            has_line_art = pipeline.line_art_allowed(raw_style)
            # A Cartoon 3D video (chosen, or what "auto" settled on) is judged
            # against its own look: ink, blur and grading are the style.
            is_cartoon_3d = raw_style == "cartoon_3d" or (
                (row["resolved_renderer"] if row else "") or "") == "cartoon_3d"

        over_cap = new_count > max_review_loops

        # Load scene-config for the review prompt (staged into the public dir above)
        scene_config_path = REMOTION_DIR / "public" / video_id / "scene-config.json"
        if not scene_config_path.exists():
            db.add_comment(DB_PATH, video_id, "agent",
                            "scene-config.json not found — skipping AI review, advancing to VIDEO_READY.")
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
            return

        with open(scene_config_path) as fh:
            scene_config_dict = json.load(fh)

        # Runs even when over_cap — TMDEV-58: the render that actually ships still gets a fresh
        # review instead of shipping with the previous round's stale gemini_feedback.
        # ai_review.py is deliberately DB-free, so the settings-table values
        # are read here and passed in rather than looked up in there (VQA-7).
        result_review = ai_review.run_ai_review(output_path, scene_config_dict,
                                                 script_text=script_text, tts_text=tts_text,
                                                 model=_setting("ai_review_model", "gemini-2.5-flash"),
                                                 fps=_setting("ai_review_fps", "10"),
                                                 api_key=gemini_api_key,
                                                 canvas=canvas,
                                                 figures=has_figures,
                                                 line_art=has_line_art,
                                                 cartoon_3d=is_cartoon_3d)
        # Every paid review is recorded — a second loop costs a second row, and
        # a reply that failed to parse was still billed (TMDEV-107).
        review_usage = result_review.get("usage")
        if review_usage:
            tusage.record_usage(DB_PATH, service="gemini",
                                model=review_usage.get("model") or "", operation="ai_review",
                                units=tusage.gemini_units(review_usage.get("usageMetadata")),
                                raw=review_usage, videos=[video_id])
        feedback = result_review.get("feedback") or ""
        db.update_fields(DB_PATH, video_id, gemini_feedback=feedback)

        must_fix = result_review.get("must_fix") or []
        suggestions = result_review.get("suggestions") or []

        if "error" in result_review:
            # Routing first, error second. Every other branch below already
            # leads with what happened to the video; this one used to end with
            # it, so a long Gemini error (httpx embeds the whole request URL)
            # truncated the "advancing to VIDEO_READY" clause away and left a
            # comment that never said where the video went.
            db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
                f"AI review failed — advancing to VIDEO_READY. "
                f"Error: {result_review['error'] or ''}"))
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
        elif over_cap:
            db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
                f"Max AI reviews ({max_review_loops}) reached — accepting as VIDEO_READY "
                f"regardless of findings:\n{feedback}"))
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
        elif must_fix or suggestions:
            db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
                f"AI review {new_count} of {max_review_loops} found {len(must_fix)} "
                f"must-fix, {len(suggestions)} suggestions:\n{feedback}"))
            db.set_status(DB_PATH, video_id, "REVISION_REQUESTED", only_if="RENDERING")
        else:
            db.add_comment(DB_PATH, video_id, "agent", _truncate_comment(
                f"AI review {new_count} of {max_review_loops} — clean: {feedback}"))
            db.set_status(DB_PATH, video_id, "VIDEO_READY", only_if="RENDERING")
    except Exception as exc:
        log.error(f"[{video_id}] unexpected error in render tail: {exc}", extra={"video_id": video_id})
        try:
            db.add_comment(DB_PATH, video_id, "agent", f"Unexpected error in render tail: {exc}")
        except Exception:
            pass
        try:
            db.set_status(DB_PATH, video_id, "REVISION_REQUESTED", only_if="RENDERING")
        except Exception as exc2:
            log.error(f"[{video_id}] also failed to set REVISION_REQUESTED: {exc2}", extra={"video_id": video_id})


def _handle_render_failure(video_id: str, error_msg: str, retry_status: str = "REVISION_REQUESTED") -> None:
    """Increment render_fail_count; escalate to FAILED past the cap, else
    move to retry_status (REVISION_REQUESTED for a real render crash — the
    agent likely needs to fix something; RENDER_QUEUED for a timeout — see
    the caller in _stage_and_render)."""
    error_msg = _truncate_comment(error_msg)
    try:
        # Atomically increment render_fail_count — capped by max_render_retries
        # so a persistently crashing render doesn't cycle forever with no
        # backstop. Since VQA-7 that key caps render retries ONLY; the AI
        # review loop has its own (ai_review_max_loops).
        with db.conn(DB_PATH) as con:
            con.execute(
                "UPDATE videos SET render_fail_count = render_fail_count + 1, updated_at = ? WHERE id = ?",
                (db._now(), video_id),
            )
            row = con.execute("SELECT render_fail_count FROM videos WHERE id = ?", (video_id,)).fetchone()
            fail_count = row["render_fail_count"] if row else 1

        max_render_retries = _max_render_retries()

        if fail_count > max_render_retries:
            db.add_comment(DB_PATH, video_id, "agent",
                            f"Render failed {fail_count} times (limit {max_render_retries}) — "
                            f"giving up. Last error: {error_msg}")
            db.set_status(DB_PATH, video_id, "FAILED", only_if="RENDERING")
        else:
            db.add_comment(DB_PATH, video_id, "agent", f"Render failed: {error_msg}")
            db.set_status(DB_PATH, video_id, retry_status, only_if="RENDERING")
    except Exception as exc:
        log.error(f"[{video_id}] failed to update DB after render failure: {exc}", extra={"video_id": video_id})


def main() -> None:
    # Mirrors entrypoint.sh's umask — keeps every file the renderer writes into
    # the bind-mounted /output_videos host-writable/deletable.
    os.umask(0)
    pipeline._init_db(DB_PATH)
    # Adds a JSONL file handler *alongside* the stdout one configured above —
    # `docker compose logs tubematic-renderer` has to keep working unchanged.
    # A missing or unwritable /logs leaves this a no-op.
    tlog.setup_json_logging(
        "renderer", LOG_DIR,
        retention_days=pipeline.log_retention_days(DB_PATH),
        secrets=pipeline.log_secret_provider(DB_PATH),
    )
    log.info("render agent starting")
    # Here and not in tubematic-worker: a RENDERING row is orphaned only when
    # THIS process died. The worker restarting says nothing about a render
    # still running in this container.
    _reconcile_rendering_videos()
    # Before the first claim, so no render ever runs on an unverified GPU,
    # and every container start (which is when a GPU change applies) leaves
    # a fresh answer for the dashboard.
    _run_gpu_probe(reason="the renderer started")
    _ensure_stills_server()

    while True:
        _sweep_gpu_probe()
        _ensure_stills_server()

        video_id = _claim_next()
        if video_id:
            _render_claimed(video_id)
        else:
            time.sleep(POLL_INTERVAL_SECS)



def _render_claimed(video_id: str) -> None:
    """One claimed video, with a boundary: whatever _stage_and_render lets
    escape (an OSError from a disk or an executable, a bug) is this video's
    failure, recorded and retried as a stall is, never the renderer's exit with
    the row left RENDERING until the container restarts."""
    try:
        _stage_and_render(video_id)
    except Exception as exc:  # noqa: BLE001 — the boundary itself
        log.exception(f"[{video_id}] the render raised: {exc}", extra={"video_id": video_id})
        _handle_render_failure(video_id, f"The renderer hit an error: {exc}", retry_status="RENDER_QUEUED")


if __name__ == "__main__":
    main()
