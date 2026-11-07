"""Cartoon 3D authoring tools: the gates, the checks and the stills an agent
needs to author a Cartoon 3D world as data, and the readiness check that keeps
an ungated world from reaching a render.

A Cartoon 3D video is one installed "Cartoon3D" scene whose props carry
the world, the beat sheet and the scene options (renderer/remotion/src/spike/
inked3d/probe2). Everything that judges that data runs in the renderer's Node
command lines, bundled by renderer/remotion/cartoon-tools/build.mjs into
cartoon-tools/dist/*.mjs; this module runs the right command line over the
video's job directory and keeps every verdict there, where validate_job and
submit_render read it back:

  <jobs>/<vid>/cartoon/gate/verdict.json           the part gate (+ stills, judge prompts)
  <jobs>/<vid>/cartoon/beatgate/beat-verdict.json  the beat gate (+ stills, judge prompt)
  <jobs>/<vid>/cartoon/stills/fNNNN.png            full-composition stills the author asked for

The rule the tools enforce is the spike's: the author never grades its own
work. A judge is a fresh model call that sees only the prompt and the stills;
here it reads the stills with cartoon_read_still and records its own answers
with the record tools, so the author's hands never touch the verdict.

Where the stills render: the render worker runs a stills server inside
tubematic-renderer, the one container with the GPU, serving the shared /jobs
volume as its public directory (renderer/remotion/cartoon-tools/stills-server.mjs);
the command lines post their stills to it (TUBEMATIC_STILLS_SERVER) and the
PNGs land under the job directory both containers share. When the server
does not answer, the command line renders the stills here, on software GL,
over the same directory (CARTOON_PUBLIC_DIR), so nothing is staged either way
and a video's files are always /public/<vid>/... to the composition.

Nothing here executes agent-authored code: the command lines run the
renderer's own TypeScript over JSON the agent wrote.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

from tubematic_core import jobfiles as tjobs

CARTOON_SCENE_SRC = "Cartoon3D"
CARTOON_DIR = "cartoon"
GATE_DIR, BEATGATE_DIR, STILLS_DIR = "gate", "beatgate", "stills"
STILL_KINDS = (GATE_DIR, BEATGATE_DIR, STILLS_DIR)

# A still's name is a path component under the cartoon directory and nothing
# else: the command lines name them (<part>-quarter.png, beat03-f0184.png,
# f0460.png) and a judge passes the name straight back.
STILL_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,80}\.png$")
MAX_STILLS_PER_CALL = 6
MAX_FRAME = 100_000

# Wall-clock ceilings. A gate run bundles the project once (~20 s cold) and
# renders a few stills at a few seconds each on software GL; fifteen beat
# stills were measured at 46 s on a GPU host, so this is headroom for a slow
# container rather than a limit anyone should hit. Checks render nothing.
CLI_TIMEOUT_SECS = 900
CHECK_TIMEOUT_SECS = 180
BUILD_TIMEOUT_SECS = 120

_build_lock = threading.Lock()
_built: set[str] = set()
# One staging per video at a time: two concurrent gate runs for one video would
# stage into the same public directory and one would delete it from under the
# other. The caller is told rather than blocked.
_busy: set[str] = set()
_busy_lock = threading.Lock()


class CartoonError(Exception):
    """A refusal with a reason the agent can act on."""


# ── The scene ───────────────────────────────────────────────────────────────

def cartoon_scene(config) -> dict | None:
    """The Cartoon 3D scene of a scene-config object, or None."""
    scenes = config.get("scenes") if isinstance(config, dict) else None
    if not isinstance(scenes, list):
        return None
    for scene in scenes:
        if isinstance(scene, dict) and scene.get("src") == CARTOON_SCENE_SRC:
            return scene
    return None


def is_cartoon(config) -> bool:
    return cartoon_scene(config) is not None


def cartoon_dir(jobs_dir, video_id: str) -> Path:
    return tjobs.job_dir(jobs_dir, video_id) / CARTOON_DIR


def still_file(jobs_dir, video_id: str, kind: str, name: str) -> Path:
    """Where a still named by a command line (or a judge) lives. Raises
    CartoonError on a name that is not a plain file name."""
    if kind not in STILL_KINDS:
        raise CartoonError(f"kind must be one of {list(STILL_KINDS)}, got {kind!r}")
    if not STILL_NAME_RE.match(name or ""):
        raise CartoonError(f"a still is named like 'beat03-f0184.png' or 'bollard-quarter.png', got {name!r}")
    return cartoon_dir(jobs_dir, video_id) / kind / name


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
        raise CartoonError(f"{video_id} is not a Cartoon 3D video: its scene-config has no {CARTOON_SCENE_SRC} scene")
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

    def __enter__(self) -> Path:
        with _busy_lock:
            if self.video_id in _busy:
                raise CartoonError(f"another Cartoon 3D tool is still running for {self.video_id}; wait for it")
            _busy.add(self.video_id)
        try:
            _job_files(self.jobs_dir, self.video_id)
        except Exception:
            with _busy_lock:
                _busy.discard(self.video_id)
            raise
        return self.dir

    def __exit__(self, *exc) -> None:
        with _busy_lock:
            _busy.discard(self.video_id)


# ── The tools ───────────────────────────────────────────────────────────────

def catalog(remotion_dir: Path) -> str:
    proc = run_cli(remotion_dir, "catalog", [], timeout=CHECK_TIMEOUT_SECS)
    if proc.returncode != 0:
        raise CartoonError(f"the catalog could not be read: {_fail_text(proc)}")
    return proc.stdout.strip()


_FINDING = re.compile(r"^\s*\[(BLOCK|ADVISE)\]\s*(.*)$")


def qa(jobs_dir, video_id: str, remotion_dir: Path) -> dict:
    """The deterministic frame check over every frame of the written
    scene-config: {passed, blocking, advisories, findings[]}."""
    path, _ = _read_config(jobs_dir, video_id)
    proc = run_cli(remotion_dir, "qa-config", [str(path)], timeout=CHECK_TIMEOUT_SECS)
    if proc.returncode not in (0, 2):
        raise CartoonError(f"the frame check could not run: {_fail_text(proc)}")
    findings = []
    for line in (proc.stdout or "").splitlines():
        m = _FINDING.match(line)
        if m:
            findings.append({"gate": m.group(1).lower(), "detail": m.group(2)})
    blocking = sum(1 for f in findings if f["gate"] == "block")
    return {"passed": proc.returncode == 0 and blocking == 0, "blocking": blocking,
            "advisories": len(findings) - blocking, "findings": findings,
            "summary": (proc.stdout or "").strip().splitlines()[0] if proc.stdout else ""}


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


def _gate_outdir(jobs_dir, video_id: str) -> Path:
    return cartoon_dir(jobs_dir, video_id) / GATE_DIR


def _gate_state(jobs_dir, video_id: str) -> dict:
    """Per part: status and, when a judge is owed, the prompt text."""
    outdir = _gate_outdir(jobs_dir, video_id)
    verdicts = outdir / "verdict.json"
    parts = json.loads(verdicts.read_text(encoding="utf-8")).get("parts", {}) if verdicts.is_file() else {}
    out = {}
    for name, rec in parts.items():
        attempts = rec.get("attempts") or []
        last = attempts[-1] if attempts else {}
        status = "pass" if rec.get("pass") else ("awaiting judge" if last.get("stage") == "stills" else "fail")
        entry = {"status": status, "attempts": len([a for a in attempts if a.get("stage") == "judge"]),
                 "errors": last.get("errors") or [], "stills": [Path(s).name for s in last.get("stills") or []]}
        if last.get("answers"):
            entry["answers"] = last["answers"]
            entry["seen"] = last.get("seen", "")
        prompt = last.get("prompt")
        if status == "awaiting judge" and prompt and Path(prompt).is_file():
            entry["judge_prompt"] = _prompt_for_judge(Path(prompt).read_text(encoding="utf-8"), jobs_dir, video_id, GATE_DIR,
                                                      f'cartoon_gate_record("{video_id}", "{name}", <your JSON>)')
        out[name] = entry
    return out


def gate(jobs_dir, video_id: str, remotion_dir: Path) -> dict:
    """The part gate over the written scene-config's own parts and cast."""
    path, _ = _read_config(jobs_dir, video_id)
    outdir = _gate_outdir(jobs_dir, video_id)
    outdir.mkdir(parents=True, exist_ok=True)
    with _Staged(jobs_dir, video_id, remotion_dir):
        proc = run_cli(remotion_dir, "gate", [str(path), str(outdir)], timeout=CLI_TIMEOUT_SECS, public_dir=Path(jobs_dir))
    if proc.returncode not in (0, 2):
        raise CartoonError(f"the part gate could not run: {_fail_text(proc)}")
    parts = _gate_state(jobs_dir, video_id)
    return {"passed": proc.returncode == 0, "parts": parts,
            "summary": "no agent-made parts or cast in this world: nothing to gate" if not parts else
            f"{sum(1 for p in parts.values() if p['status'] == 'pass')} of {len(parts)} pass; "
            f"{sum(1 for p in parts.values() if p['status'] == 'awaiting judge')} awaiting a judge"}


def gate_record(jobs_dir, video_id: str, remotion_dir: Path, part: str, answers: dict) -> dict:
    path, _ = _read_config(jobs_dir, video_id)
    if not re.match(r"^[a-z][A-Za-z0-9]{1,31}$", part or ""):
        raise CartoonError(f"part must be a part or cast name, got {part!r}")
    if not isinstance(answers, dict):
        raise CartoonError("answers must be the judge's JSON object")
    outdir = _gate_outdir(jobs_dir, video_id)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(answers, fh)
        answers_file = fh.name
    try:
        proc = run_cli(remotion_dir, "gate", [str(path), str(outdir), "--record", part, answers_file], timeout=CHECK_TIMEOUT_SECS)
    finally:
        os.unlink(answers_file)
    if proc.returncode not in (0, 2):
        raise CartoonError(_fail_text(proc))
    state = _gate_state(jobs_dir, video_id).get(part, {})
    return {"part": part, "passed": proc.returncode == 0, **state}


def _beatgate_outdir(jobs_dir, video_id: str) -> Path:
    return cartoon_dir(jobs_dir, video_id) / BEATGATE_DIR


def _beat_status(jobs_dir, video_id: str, remotion_dir: Path, staged: Path) -> dict:
    proc = run_cli(remotion_dir, "beatgate", [str(staged), str(_beatgate_outdir(jobs_dir, video_id)), "--status"],
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


def beat_gate(jobs_dir, video_id: str, remotion_dir: Path) -> dict:
    """One still per beat and the judges' prompt; the status when the stills exist."""
    _read_config(jobs_dir, video_id)
    outdir = _beatgate_outdir(jobs_dir, video_id)
    outdir.mkdir(parents=True, exist_ok=True)
    with _Staged(jobs_dir, video_id, remotion_dir) as staged:
        proc = run_cli(remotion_dir, "beatgate", [str(staged), str(outdir)], timeout=CLI_TIMEOUT_SECS, props=_props(video_id),
                       public_dir=Path(jobs_dir))
        if proc.returncode not in (0, 2):
            raise CartoonError(f"the beat gate could not run: {_fail_text(proc)}")
        return _beat_status(jobs_dir, video_id, remotion_dir, staged)


def beat_gate_record(jobs_dir, video_id: str, remotion_dir: Path, answers: dict) -> dict:
    _read_config(jobs_dir, video_id)
    if not isinstance(answers, dict) or not isinstance(answers.get("beats"), list):
        raise CartoonError("answers must be the judge's JSON object with a beats list")
    outdir = _beatgate_outdir(jobs_dir, video_id)
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(answers, fh)
        answers_file = fh.name
    try:
        with _Staged(jobs_dir, video_id, remotion_dir) as staged:
            proc = run_cli(remotion_dir, "beatgate", [str(staged), str(outdir), "--record", answers_file],
                           timeout=CHECK_TIMEOUT_SECS, props=_props(video_id), public_dir=Path(jobs_dir))
            if proc.returncode not in (0, 2):
                raise CartoonError(_fail_text(proc))
            status = _beat_status(jobs_dir, video_id, remotion_dir, staged)
    finally:
        os.unlink(answers_file)
    status["recorded"] = (proc.stdout or "").strip().splitlines()[:len(answers["beats"])]
    return status


# ── Readiness: what validate_job and submit_render ask ──────────────────────

def readiness(jobs_dir, video_id: str, remotion_dir: Path) -> list[str]:
    """Why this Cartoon 3D video must not render yet: parts without a PASS for
    their current spec, a beat sheet without its two judges' PASS, frames the
    deterministic check blocks. Empty when it may. Renders nothing."""
    path, _ = _read_config(jobs_dir, video_id)
    errors: list[str] = []
    proc = run_cli(remotion_dir, "gate", [str(path), str(_gate_outdir(jobs_dir, video_id)), "--check"], timeout=CHECK_TIMEOUT_SECS)
    if proc.returncode not in (0, 2):
        errors.append(f"Cartoon 3D part gate could not be checked: {_fail_text(proc)}")
    else:
        missing = _last_json(proc.stdout).get("unpassed", [])
        if missing:
            errors.append("Cartoon 3D parts without a judge's PASS for their current spec: " + ", ".join(missing)
                          + " — call cartoon_gate, have a fresh judge answer each prompt, and record its verdict")
    with _Staged(jobs_dir, video_id, remotion_dir) as staged:
        status = _beat_status(jobs_dir, video_id, remotion_dir, staged)
    if not status["passed"]:
        errors.append("Cartoon 3D beat gate: " + status["summary"] + (
            "" if status["need"] is None else " — call cartoon_beat_gate and have fresh judges answer"))
    check = qa(jobs_dir, video_id, remotion_dir)
    if check["blocking"]:
        first = "; ".join(f["detail"] for f in check["findings"] if f["gate"] == "block")[:600]
        errors.append(f"Cartoon 3D frame check blocks {check['blocking']} finding(s): {first}")
    return errors
