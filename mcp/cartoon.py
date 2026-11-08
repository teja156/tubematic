"""Cartoon 3D authoring tools (TMDEV-185): the stills an agent looks at while
it writes a Cartoon 3D Short as code, the beat gate that judges the result,
the soundtrack synthesised from a spec, the kit source it reads, and the
readiness check that keeps an ungated video from reaching a render.

A Cartoon 3D video is one generated scene spanning the whole video, whose
TypeScript the agent writes per video under scenes/generated/<video_id>/
(a `CartoonShort.tsx` that mounts the renderer's runner with the video's
VideoDef, and the `.ts` modules beside it: story, sets, staging), and whose
scene-config entry carries `props.cartoon3d.beats`: the shots as beats for the
beat gate. The renderer's frozen kit (renderer/remotion/src/cartoon3d/) is
what that code is written against; nothing in this module executes the
agent's code itself. The command lines that render stills and judge beats are
the renderer's own TypeScript, bundled by renderer/remotion/cartoon-tools/
build.mjs into cartoon-tools/dist/*.mjs; this module runs the right one over
the video's job directory and keeps every verdict there, where validate_job
and submit_render read it back:

  <jobs>/<vid>/cartoon/beatgate/beat-verdict.json  the beat gate (+ stills, judge prompt)
  <jobs>/<vid>/cartoon/stills/fNNNN.png            full-composition stills the author asked for
  <jobs>/<vid>/cartoon/audio/                      audio-spec.json, voice.wav and mix/ (mix.wav, stems, cues.md)

The rule the tools enforce is the spike's: the author never grades its own
work. A judge is a fresh model call that sees only the prompt and the stills;
here it reads the stills with cartoon_read_still and records its own answers
with cartoon_beat_gate_record, so the author's hands never touch the verdict.
The verdict is keyed by a hash of the video's source files, its beats and the
narration per beat: an edit to the code is judged again.

Where the stills render: the render worker runs a stills server inside
tubematic-renderer, the one container with the GPU, serving the shared /jobs
volume as its public directory and re-bundling when the generated source tree
changes (renderer/remotion/cartoon-tools/stills-server.mjs); the command lines
post their stills to it (TUBEMATIC_STILLS_SERVER) and the PNGs land under the
job directory both containers share. When the server does not answer, the
command line renders the stills here, on software GL, over the same
directory (CARTOON_PUBLIC_DIR), so nothing is staged either way and a video's
files are always /public/<vid>/... to the composition.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from tubematic_core import jobfiles as tjobs

# The scene-config marker of a Cartoon 3D scene: scenes[i].props.cartoon3d = {beats: [...]}.
# Keep in sync with renderer/remotion/src/cartoon3d/gate/sceneConfig.ts and worker.py.
CARTOON_PROPS = "cartoon3d"
# The module the scene-config's `src` names: <video_id>/CartoonShort (a .tsx the agent writes).
ENTRY_SCENE = "CartoonShort"
CARTOON_DIR = "cartoon"
BEATGATE_DIR, STILLS_DIR, AUDIO_DIR = "beatgate", "stills", "audio"
STILL_KINDS = (BEATGATE_DIR, STILLS_DIR)
MIX_DIR = "mix"
MIX_WAV = "mix.wav"
SOURCE_RECORD = "source.json"      # <cartoon>/source.json: the fingerprint of the source submit_render queued

# A still's name is a path component under the cartoon directory and nothing
# else: the command lines name them (beat03-f0184.png, f0460.png) and a judge
# passes the name straight back.
STILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}\.png$")
MAX_STILLS_PER_CALL = 6
MAX_FRAME = 100_000

# The kit source an agent may read: everything under src/cartoon3d/ except tests and the gate.
KIT_PATH_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*(/[A-Za-z0-9][A-Za-z0-9_.-]*)*$")
KIT_SRC = "src/cartoon3d"

# Wall-clock ceilings. A beat gate bundles the project once (~20 s cold) and
# renders a still per beat at a few seconds each on the GPU server; forty on
# software GL were measured under ten minutes. The soundtrack synthesises a
# two-minute mix in about a minute of numpy. Checks render nothing.
CLI_TIMEOUT_SECS = 1200
CHECK_TIMEOUT_SECS = 180
BUILD_TIMEOUT_SECS = 120
SOUNDTRACK_TIMEOUT_SECS = 900

_build_lock = threading.Lock()
_built: set[str] = set()
# One rendering tool per video at a time: two concurrent beat-gate runs for one
# video would write the same verdict file. The caller is told rather than blocked.
_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()
# How long a recorder waits for a rendering tool or another recorder on the
# same video. Judges answer in parallel; their record calls queue here rather
# than lose a verdict (two writers of one verdict file keep only the last).
RECORD_WAIT_SECS = CHECK_TIMEOUT_SECS


def _lock_for(video_id: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(video_id, threading.Lock())


class _Recording:
    """The per-video lock, waited for: a recorder queues behind a gate render
    or another recorder instead of being refused, so parallel judges all land."""

    def __init__(self, video_id: str):
        self.video_id = video_id
        self.lock = _lock_for(video_id)

    def __enter__(self) -> None:
        if not self.lock.acquire(timeout=RECORD_WAIT_SECS):
            raise CartoonError(f"another Cartoon 3D tool has been running for {self.video_id} for over "
                               f"{RECORD_WAIT_SECS} s; try again")

    def __exit__(self, *exc) -> None:
        self.lock.release()


class CartoonError(Exception):
    """A refusal with a reason the agent can act on."""


# ── The scene ───────────────────────────────────────────────────────────────

def cartoon_scene(config) -> dict | None:
    """The Cartoon 3D scene of a scene-config object (the scene whose props
    carry `cartoon3d` with a beats list), or None."""
    scenes = config.get("scenes") if isinstance(config, dict) else None
    if not isinstance(scenes, list):
        return None
    for scene in scenes:
        props = scene.get("props") if isinstance(scene, dict) else None
        c3d = props.get(CARTOON_PROPS) if isinstance(props, dict) else None
        if isinstance(c3d, dict) and isinstance(c3d.get("beats"), list):
            return scene
    return None


def is_cartoon(config) -> bool:
    return cartoon_scene(config) is not None


def cartoon_dir(jobs_dir, video_id: str) -> Path:
    return tjobs.job_dir(jobs_dir, video_id) / CARTOON_DIR


def mix_file(jobs_dir, video_id: str) -> Path:
    """Where the synthesised soundtrack lands; the worker muxes it when it is
    newer than the voice (keep in sync with worker.py)."""
    return cartoon_dir(jobs_dir, video_id) / AUDIO_DIR / MIX_DIR / MIX_WAV


def still_file(jobs_dir, video_id: str, kind: str, name: str) -> Path:
    """Where a still named by a command line (or a judge) lives. Raises
    CartoonError on a name that is not a plain file name."""
    if kind not in STILL_KINDS:
        raise CartoonError(f"kind must be one of {list(STILL_KINDS)}, got {kind!r}")
    if not STILL_NAME_RE.match(name or ""):
        raise CartoonError(f"a still is named like 'beat03-f0184.png' or 'f0460.png', got {name!r}")
    return cartoon_dir(jobs_dir, video_id) / kind / name


def source_dir(scenes_dir, video_id: str) -> Path:
    """The video's generated source tree, scenes/generated/<video_id>/."""
    try:
        return tjobs.scene_dir(scenes_dir, video_id)
    except tjobs.UnsafePath as e:
        raise CartoonError(str(e))


def _utcnow() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check_source(scenes_dir, video_id: str) -> Path:
    src = source_dir(scenes_dir, video_id)
    entry = src / f"{ENTRY_SCENE}.tsx"
    if not src.is_dir() or not entry.is_file():
        raise CartoonError(f"{video_id} has no generated source yet: write {video_id}/{ENTRY_SCENE} (and its modules) "
                           f"with write_scene_file first")
    try:
        # a symlink in the tree would be followed here, by the bundler and by the
        # worker while the gate's hash and the stills server skip it: refused outright
        tjobs.source_fingerprint(src)
    except tjobs.UnsafePath as e:
        raise CartoonError(f"{video_id}'s generated source: {e}")
    return src


def freeze_source(jobs_dir, video_id: str, scenes_dir) -> str:
    """Record the fingerprint of the source submit_render is queueing, under
    <cartoon>/source.json; the worker refuses to render any other tree."""
    src = _check_source(scenes_dir, video_id)
    fp = tjobs.source_fingerprint(src)
    record = cartoon_dir(jobs_dir, video_id) / SOURCE_RECORD
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({"fingerprint": fp, "at": _utcnow()}), encoding="utf-8")
    return fp


# ── Running the command lines ───────────────────────────────────────────────

def _node() -> str:
    node = shutil.which("node")
    if not node:
        raise CartoonError("node is not on PATH in the MCP container; the Cartoon 3D tools cannot run")
    return node


def ensure_built(remotion_dir: Path) -> None:
    """Build cartoon-tools/dist once per process (about a second; idempotent)."""
    key = str(remotion_dir)
    dist = remotion_dir / "cartoon-tools" / "dist"
    with _build_lock:
        if key in _built and dist.is_dir():
            return
        build = remotion_dir / "cartoon-tools" / "build.mjs"
        if not build.is_file():
            raise CartoonError(f"{build} is missing: the renderer checkout has no Cartoon 3D tools")
        proc = subprocess.run([_node(), str(build)], cwd=str(remotion_dir), capture_output=True, text=True,
                              timeout=BUILD_TIMEOUT_SECS)
        if proc.returncode != 0:
            raise CartoonError(f"building the Cartoon 3D tools failed: {(proc.stderr or proc.stdout).strip()[-600:]}")
        _built.add(key)


def _env(remotion_dir: Path, props: dict | None = None, public_dir: Path | None = None) -> dict:
    env = dict(os.environ)
    env["REMOTION_ROOT"] = str(remotion_dir)
    if public_dir is not None:
        env["CARTOON_PUBLIC_DIR"] = str(public_dir)
        server = os.getenv("TUBEMATIC_STILLS_SERVER", "").strip()
        if server:
            env["STILLS_SERVER"] = server
    # the container's Chromium, as the text audit uses it; a host without the
    # variable lets Remotion use its own browser
    browser = os.getenv("PUPPETEER_EXECUTABLE_PATH")
    if browser and "CARTOON_BROWSER" not in env:
        env["CARTOON_BROWSER"] = browser
    if props is not None:
        env["BEAT_PROPS"] = json.dumps(props)
    return env


def run_cli(remotion_dir: Path, name: str, args: list[str], *, timeout: int, props: dict | None = None,
            public_dir: Path | None = None) -> subprocess.CompletedProcess:
    ensure_built(remotion_dir)
    cli = remotion_dir / "cartoon-tools" / "dist" / f"{name}.mjs"
    try:
        return subprocess.run([_node(), str(cli), *args], cwd=str(remotion_dir), env=_env(remotion_dir, props, public_dir),
                              capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        raise CartoonError(f"the {name} tool did not finish within {timeout} s")


def _last_json(stdout: str) -> dict:
    """The command lines print one JSON line last; Remotion may print browser
    chatter before it."""
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    raise CartoonError(f"no JSON in the tool's output: {(stdout or '').strip()[-300:]!r}")


def _fail_text(proc: subprocess.CompletedProcess) -> str:
    text = (proc.stderr or "").strip() or (proc.stdout or "").strip()
    return "\n".join(text.splitlines()[-8:])


# ── The video's files, as the composition sees them ─────────────────────────

def _props(video_id: str) -> dict:
    """The Composition's props: the jobs volume is the public directory, so the
    video's files are /public/<vid>/..., the layout the worker renders from."""
    return {"sceneConfigPath": f"/public/{video_id}/scene-config.json", "timelinePath": f"/public/{video_id}/timeline.json",
            "audioPath": f"/public/{video_id}/audio.mp3", "watermark": False}


def _job_files(jobs_dir, video_id: str) -> tuple[Path, Path, Path]:
    paths = tuple(tjobs.job_file(jobs_dir, video_id, n) for n in (tjobs.SCENE_CONFIG, tjobs.TIMELINE, tjobs.AUDIO))
    for p in paths:
        if p.is_symlink():
            raise CartoonError(f"{p.name} is a symlink; refused")
        if not p.is_file():
            raise CartoonError(f"{p.name} is missing for {video_id}: " + (
                "call write_scene_config first" if p.name == tjobs.SCENE_CONFIG else "generate_voice has not run"))
    return paths  # type: ignore[return-value]


def _read_config(jobs_dir, video_id: str) -> tuple[Path, dict]:
    path = tjobs.job_file(jobs_dir, video_id, tjobs.SCENE_CONFIG)
    if path.is_symlink() or not path.is_file():
        raise CartoonError(f"{video_id} has no scene-config.json yet: call write_scene_config first")
    try:
        config = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise CartoonError(f"scene-config.json is not valid JSON: {e}")
    if not is_cartoon(config):
        raise CartoonError(f"{video_id} is not a Cartoon 3D video: no scene of its scene-config carries props.{CARTOON_PROPS}.beats")
    return path, config


class _Staged:
    """One rendering tool at a time per video (two would write the same
    verdict file), over the video's job directory, which holds the three job
    files the composition fetches. Nothing is copied: the jobs volume is the
    public directory of both the stills server and a local render."""

    def __init__(self, jobs_dir, video_id: str, remotion_dir: Path):
        self.video_id = video_id
        self.dir = tjobs.job_dir(jobs_dir, video_id)
        self.jobs_dir = jobs_dir
        self.lock = _lock_for(video_id)

    def __enter__(self) -> Path:
        if not self.lock.acquire(blocking=False):
            raise CartoonError(f"another Cartoon 3D tool is still running for {self.video_id}; wait for it")
        try:
            _job_files(self.jobs_dir, self.video_id)
        except Exception:
            self.lock.release()
            raise
        return self.dir

    def __exit__(self, *exc) -> None:
        self.lock.release()


# ── The kit source ──────────────────────────────────────────────────────────

def list_kit(remotion_dir: Path) -> list[str]:
    """Every file of the frozen kit an agent writes against, by path under
    src/cartoon3d/: the contract (video.ts), the camera grammar, the runner,
    kit/*, post/* and the worked example under examples/. Tests and the gate
    are left out."""
    root = remotion_dir / KIT_SRC
    if not root.is_dir():
        raise CartoonError(f"{root} is missing: the renderer checkout has no Cartoon 3D kit")
    out = []
    for p in sorted(root.rglob("*")):
        rel = p.relative_to(root).as_posix()
        if p.is_file() and p.suffix in (".ts", ".tsx", ".md") and ".test." not in p.name and not rel.startswith("gate/"):
            out.append(rel)
    return out


def read_kit(remotion_dir: Path, path: str) -> str:
    """One kit file's text, by the path list_kit prints."""
    if not KIT_PATH_RE.match(path or "") or ".." in path.split("/"):
        raise CartoonError(f"path must be a kit file like 'kit/cast.ts' or 'examples/chicago/story.ts', got {path!r}")
    if path not in list_kit(remotion_dir):
        raise CartoonError(f"no kit file {path!r}; cartoon_kit_list names them")
    return (remotion_dir / KIT_SRC / path).read_text(encoding="utf-8")


# ── The tools ───────────────────────────────────────────────────────────────

def stills(jobs_dir, video_id: str, remotion_dir: Path, frames: list[int]) -> list[Path]:
    """Full-composition stills at the given frames: <cartoon>/stills/fNNNN.png."""
    _read_config(jobs_dir, video_id)
    if not frames or len(frames) > MAX_STILLS_PER_CALL:
        raise CartoonError(f"frames must list 1 to {MAX_STILLS_PER_CALL} frame numbers")
    clean = []
    for f in frames:
        if isinstance(f, bool) or not isinstance(f, int) or f < 0 or f > MAX_FRAME:
            raise CartoonError(f"frames must be whole frame numbers, got {f!r}")
        clean.append(f)
    outdir = cartoon_dir(jobs_dir, video_id) / STILLS_DIR
    with _Staged(jobs_dir, video_id, remotion_dir) as staged:
        proc = run_cli(remotion_dir, "still", [str(staged), str(outdir), *map(str, clean)],
                       timeout=CLI_TIMEOUT_SECS, props=_props(video_id), public_dir=Path(jobs_dir))
    if proc.returncode != 0:
        raise CartoonError(f"the stills could not be rendered: {_fail_text(proc)}")
    return [Path(p) for p in _last_json(proc.stdout).get("stills", [])]


def _prompt_for_judge(text: str, jobs_dir, video_id: str, kind: str, record_call: str) -> str:
    """The command line's judge prompt, with its still paths turned into the
    names a judge reads through cartoon_read_still and its "write a file"
    instruction turned into the record call the judge makes itself."""
    base = str(cartoon_dir(jobs_dir, video_id) / kind)
    text = re.sub(re.escape(base) + r"/([A-Za-z0-9_-]+\.png)",
                  lambda m: f'still "{m.group(1)}" (call cartoon_read_still("{video_id}", "{kind}", "{m.group(1)}"))', text)
    return text.replace("to the file named in your instructions", f"then call {record_call} with it yourself")


def _beatgate_outdir(jobs_dir, video_id: str) -> Path:
    return cartoon_dir(jobs_dir, video_id) / BEATGATE_DIR


def _beat_args(jobs_dir, video_id: str, staged: Path, srcdir: Path, *extra: str) -> list[str]:
    return [str(staged), str(_beatgate_outdir(jobs_dir, video_id)), "--source", str(srcdir), *extra]


def _beat_status(jobs_dir, video_id: str, remotion_dir: Path, staged: Path, srcdir: Path) -> dict:
    proc = run_cli(remotion_dir, "beatgate", _beat_args(jobs_dir, video_id, staged, srcdir, "--status"),
                   timeout=CHECK_TIMEOUT_SECS, props=_props(video_id), public_dir=Path(jobs_dir))
    if proc.returncode not in (0, 2):
        raise CartoonError(f"the beat gate's status could not be read: {_fail_text(proc)}")
    s = _last_json(proc.stdout)
    out = {"passed": bool(s.get("pass")), "need": s.get("need"), "judges": s.get("judges", 0), "tie": s.get("tie", []),
           "fails": s.get("fails", []), "summary": s.get("summary", ""), "beats": s.get("beats", 0),
           "stills": [Path(p).name for p in s.get("stills") or []]}
    prompt = s.get("prompt")
    if s.get("need") and prompt and Path(prompt).is_file():
        out["judge_prompt"] = _prompt_for_judge(Path(prompt).read_text(encoding="utf-8"), jobs_dir, video_id, BEATGATE_DIR,
                                                f'cartoon_beat_gate_record("{video_id}", <your JSON>)')
    return out


def beat_gate(jobs_dir, video_id: str, remotion_dir: Path, scenes_dir) -> dict:
    """One still per beat and the judges' prompt; the status when the stills exist."""
    _read_config(jobs_dir, video_id)
    srcdir = _check_source(scenes_dir, video_id)
    outdir = _beatgate_outdir(jobs_dir, video_id)
    outdir.mkdir(parents=True, exist_ok=True)
    with _Staged(jobs_dir, video_id, remotion_dir) as staged:
        proc = run_cli(remotion_dir, "beatgate", _beat_args(jobs_dir, video_id, staged, srcdir), timeout=CLI_TIMEOUT_SECS,
                       props=_props(video_id), public_dir=Path(jobs_dir))
        if proc.returncode not in (0, 2):
            raise CartoonError(f"the beat gate could not run: {_fail_text(proc)}")
        return _beat_status(jobs_dir, video_id, remotion_dir, staged, srcdir)


def beat_gate_record(jobs_dir, video_id: str, remotion_dir: Path, scenes_dir, answers: dict) -> dict:
    _read_config(jobs_dir, video_id)
    srcdir = _check_source(scenes_dir, video_id)
    if not isinstance(answers, dict) or not isinstance(answers.get("beats"), list):
        raise CartoonError("answers must be the judge's JSON object with a beats list")
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(answers, fh)
        answers_file = fh.name
    try:
        with _Recording(video_id):
            _job_files(jobs_dir, video_id)
            staged = tjobs.job_dir(jobs_dir, video_id)
            proc = run_cli(remotion_dir, "beatgate", _beat_args(jobs_dir, video_id, staged, srcdir, "--record", answers_file),
                           timeout=CHECK_TIMEOUT_SECS, props=_props(video_id), public_dir=Path(jobs_dir))
            if proc.returncode not in (0, 2):
                raise CartoonError(_fail_text(proc))
            status = _beat_status(jobs_dir, video_id, remotion_dir, staged, srcdir)
    finally:
        os.unlink(answers_file)
    status["recorded"] = (proc.stdout or "").strip().splitlines()[:len(answers["beats"])]
    return status


# ── The soundtrack ──────────────────────────────────────────────────────────

def _check_spec(spec) -> None:
    """The shape of an audio spec, so a typo is refused with a reason here;
    the engine checks the names (generators, styles) and values itself."""
    if not isinstance(spec, dict) or not (isinstance(spec.get("music"), dict) or isinstance(spec.get("sfx"), dict)):
        raise CartoonError("spec must be an object with a 'music' and/or an 'sfx' object (the soundtrack spec of the skill)")
    music = spec.get("music")
    if music is not None:
        if not isinstance(music, dict) or not isinstance(music.get("sections"), list) or not music["sections"]:
            raise CartoonError("spec.music needs a non-empty 'sections' list ({name, start, end, style, level})")
        for i, s in enumerate(music["sections"]):
            if (not isinstance(s, dict) or not all(isinstance(s.get(k), (int, float)) and not isinstance(s.get(k), bool) for k in ("start", "end"))
                    or not isinstance(s.get("style"), str)):
                raise CartoonError(f"spec.music.sections[{i}] needs numeric start and end (seconds) and a style name")
    sfx = spec.get("sfx")
    if sfx is not None:
        if not isinstance(sfx, dict) or not isinstance(sfx.get("cues"), list):
            raise CartoonError("spec.sfx needs a 'cues' list")
        for i, c in enumerate(sfx["cues"]):
            if (not isinstance(c, dict) or not isinstance(c.get("gen"), str)
                    or not any(isinstance(c.get(k), (int, float)) and not isinstance(c.get(k), bool) for k in ("t", "f"))):
                raise CartoonError(f"spec.sfx.cues[{i}] needs a 'gen' name and a time: 't' (seconds) or 'f' (frame)")


def soundtrack(jobs_dir, video_id: str, remotion_dir: Path, spec: dict) -> dict:
    """Synthesise the soundtrack from a spec: music sections and sound-effect
    cues (cartoon-tools/audio/mix.py), mixed under the voice to the target
    loudness, exactly the video's length. Writes <cartoon>/audio/{audio-spec.json,
    voice.wav, mix/mix.wav, mix/cues.md, ...}; the worker muxes mix.wav in
    place of the bare voice when it is newer than the voice."""
    _read_config(jobs_dir, video_id)
    _check_spec(spec)
    _, timeline, audio = _job_files(jobs_dir, video_id)
    mix_py = remotion_dir / "cartoon-tools" / "audio" / "mix.py"
    if not mix_py.is_file():
        raise CartoonError(f"{mix_py} is missing: the renderer checkout has no soundtrack engine")
    python = shutil.which("python3") or shutil.which("python")
    ffmpeg = shutil.which("ffmpeg")
    if not python or not ffmpeg:
        raise CartoonError("python3 and ffmpeg must be on PATH in the MCP container for the soundtrack")
    adir = cartoon_dir(jobs_dir, video_id) / AUDIO_DIR
    with _Staged(jobs_dir, video_id, remotion_dir):
        adir.mkdir(parents=True, exist_ok=True)
        (adir / "audio-spec.json").write_text(json.dumps(spec, indent=1), encoding="utf-8")
        voice = adir / "voice.wav"
        try:
            conv = subprocess.run([ffmpeg, "-v", "error", "-y", "-i", str(audio), "-ar", "48000", "-ac", "1", str(voice)],
                                  capture_output=True, text=True, timeout=CHECK_TIMEOUT_SECS)
        except subprocess.TimeoutExpired:
            raise CartoonError("resampling the voice did not finish")
        if conv.returncode != 0 or not voice.is_file():
            raise CartoonError(f"the voice could not be resampled: {conv.stderr.strip()[-400:]}")
        out = adir / MIX_DIR
        # built beside the live mix and swapped in whole once it is complete: a
        # failed or interrupted run never leaves a partial mix.wav where the
        # worker would mux it, and the previous mix stays until the new one is
        new = adir / f"{MIX_DIR}.new"
        shutil.rmtree(new, ignore_errors=True)
        try:
            try:
                proc = subprocess.run([python, "-I", str(mix_py), "--voice", str(voice), "--timeline", str(timeline),
                                       "--spec", str(adir / "audio-spec.json"), "--out", str(new)],
                                      cwd=str(mix_py.parent), capture_output=True, text=True, timeout=SOUNDTRACK_TIMEOUT_SECS)
            except subprocess.TimeoutExpired:
                raise CartoonError(f"the soundtrack did not finish within {SOUNDTRACK_TIMEOUT_SECS} s")
            if proc.returncode != 0:
                text = _fail_text(proc)
                if "No module named" in text:
                    text += "\n(numpy and scipy must be installed in the MCP container)"
                raise CartoonError(f"the soundtrack could not be mixed: {text}")
            if not (new / MIX_WAV).is_file():
                raise CartoonError(f"mix.py finished but wrote no {MIX_WAV}: {_fail_text(proc)}")
            # published file by file into the live directory, the mix itself last and
            # by an atomic replace: the last good mix.wav is never missing or partial,
            # and a worker that already opened it keeps reading the file it opened
            out.mkdir(parents=True, exist_ok=True)
            fresh = sorted(p for p in new.iterdir() if p.is_file() and not p.is_symlink())
            for p in fresh:
                if p.name != MIX_WAV:
                    os.replace(p, out / p.name)
            os.replace(new / MIX_WAV, out / MIX_WAV)
            for stale in out.iterdir():
                if stale.is_file() and stale.name not in {p.name for p in fresh}:
                    stale.unlink()
        finally:
            shutil.rmtree(new, ignore_errors=True)
        mix = out / MIX_WAV
        # newer than the voice by construction; a re-voiced video makes this mix stale and the worker ignores it
        os.utime(mix)
        cues_md = (out / "cues.md").read_text(encoding="utf-8") if (out / "cues.md").is_file() else ""
        loud = {}
        if (out / "loudness.json").is_file():
            try:
                loud = json.loads((out / "loudness.json").read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                loud = {}
    return {"mix": str(mix), "cues": cues_md[:6000], "loudness": loud,
            "log": "\n".join((proc.stdout or "").strip().splitlines()[-12:])}


# ── Readiness: what validate_job and submit_render ask ──────────────────────

def readiness(jobs_dir, video_id: str, remotion_dir: Path, scenes_dir) -> list[str]:
    """Why this Cartoon 3D video must not render yet: no generated source, or
    a beat sheet without its two judges' PASS for the current source. Empty
    when it may. Renders nothing."""
    _read_config(jobs_dir, video_id)
    try:
        srcdir = _check_source(scenes_dir, video_id)
    except CartoonError as e:
        return [f"Cartoon 3D source: {e}"]
    with _Staged(jobs_dir, video_id, remotion_dir) as staged:
        status = _beat_status(jobs_dir, video_id, remotion_dir, staged, srcdir)
    if status["passed"]:
        return []
    return ["Cartoon 3D beat gate: " + status["summary"] + (
        "" if status["need"] is None else " — call cartoon_beat_gate and have fresh judges answer")]
