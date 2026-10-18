#!/usr/bin/env python3
"""Deterministic pre-render text-layout audit (VQA-9).

Renders a handful of settled frames of each scene in headless Chromium — via
the Remotion Node API, producing no image at all — and reports text-vs-text
collisions and safe-zone breaches using real measured text rects.

Why this exists: the AI review was measured against three deliberate-defect
fixtures. It handles safe-zone and off-screen text adequately, but it is BLIND
to text-on-text overlap — 0 of 2 caught, including two headlines printed
directly on top of each other, which it read and quoted by name while
reporting a *position* problem instead. Overlap is geometrically decidable, so
guessing at it is the wrong tool.

Division of labour, deliberate and load-bearing:

  renderer/remotion/src/audit/TextLayoutProbe.tsx   measures (rects + opacity)
  renderer/remotion/audit/run-text-layout-audit.mjs drives Remotion
  THIS FILE                                         decides what is a violation

Every threshold lives here, because this is the only layer with test coverage:
renderer/remotion/ has no JS test runner at all -- its devDeps are eslint,
prettier and typescript, and `lint` (eslint src && tsc) is its only gate, so
adding jest/vitest there means a new devDep and a Dockerfile-invalidating
npm ci. Do not move a threshold into the probe.

An earlier version of this note blamed the dev host's Node 18 against
Remotion's >= 20. Node 22 was installed under nvm on 2026-08-22 and both
layers typecheck clean there now -- but the split stands unchanged on the
missing-test-runner argument above. Do not read the Node upgrade as lifting
this constraint.

ADVISORY ONLY. validate_job surfaces these under "warnings" and never lets them
affect "passed". Routing them through AI-review feedback instead would put them
under the "any finding loops to REVISION_REQUESTED" rule, where one systematic
false positive wedges every video in a revision loop.
"""

import json
import os
import shutil
import signal
import subprocess
import tempfile
import threading
from pathlib import Path

from tubematic_core import jobfiles as tjobs

# ── Tunables ────────────────────────────────────────────────────────────────

# Frames to skip at a scene's start before its content is considered settled.
# 1.5s at 30fps, sized from the real entrance ramps in the codebase: the
# scene-config skill's ex-ken-burns.tsx subhead finishes at frame 40, its
# headline at 20, ex-hybrid-anchored.tsx at 24, KenBurnsImage's caption at 18,
# and both regression fixtures fade in over [0, 15]. Sampling frame 0 instead
# would measure text that is invisible AND displaced ~70px by a spring — a
# guaranteed false positive.
ENTRANCE_ALLOWANCE_FRAMES = 45

# Crossfade length when a scene doesn't specify one.
# Keep in sync with DEFAULT_FADE in renderer/remotion/src/CompositionBuilder.tsx.
DEFAULT_FADE_FRAMES = 8

# Frames sampled per scene, spread across its settled window. More than one
# because no single settled frame fits every scene type: StepFlowDiagram is laid
# out fully at frame 0, but an ImageFX scene with a project() overlay moves
# continuously with the pan and TextRevealScene reflows every frame as words
# accumulate. Sampling uniformly avoids classifying scene types, which is
# impossible anyway — whether a generated scene uses ImageFX's render-prop form
# is not visible in scene-config.json. At ~70ms per frame (measured) a 15-scene
# video costs about 5s of frame time.
SAMPLES_PER_SCENE = 5

# Elements fainter than this are ignored: an entrance/crossfade ramp routinely
# leaves text at low opacity where a collision is not visible to a viewer.
OPACITY_FLOOR = 0.9

# Overlap is reported when the intersection covers at least this fraction of the
# smaller element's measured text box. MEASURED against the text-overlap.tsx
# regression fixture in-container: A (two headlines 24px apart) 0.73, B (a label
# across a caption) 0.60, C (the close-but-clean negative control) 0.00.
#
# B is the tightest true positive, so this has to stay well under 0.60. TUNABLE,
# but re-measure against the fixture rather than trusting this comment.
OVERLAP_MIN_FRACTION = 0.15

# Canvas and YouTube Shorts safe zone. Keep in sync with SAFE_ZONE in
# mcp/server.py, SAFE in renderer/remotion/src/scenes/TextRevealScene.tsx,
# SAFE_ZONE_TOP/BOTTOM in renderer/api/ai_review.py, and the prose form in the
# tubematic-scene-config skill. Cross-process duplication is this repo's
# convention; the sync comments are the mechanism.
FRAME_WIDTH = 1080
FRAME_HEIGHT = 1920
SAFE_ZONE = {"top": 150, "bottom": 170, "left": 60, "right": 60}

# Slack allowed before a rect counts as leaving the safe zone. Small on purpose:
# the probe reports glyph-tight Range rects, so this absorbs sub-pixel layout
# rounding only, not a systematic offset.
SAFE_ZONE_TOLERANCE_PX = 2.0

# Wall-clock ceiling for the whole audit. Measured on the live renderer: a warm
# bundle plus one frame is 3-4s and 15 frames total 5s, so this is generous
# headroom for a COLD bundle rather than a limit anyone should hit.
#
# Deliberately a constant, and deliberately NOT settings.render_timeout_secs:
# that key is read by renderer/api/worker.py in the tubematic-renderer container
# and is not in this code path at all. Raising it would do nothing for the audit
# while loosening the render's own guard.
TEXT_AUDIT_TIMEOUT_SECS = 180

# Longest text excerpt echoed into a warning line. Long enough that a headline
# from a real scene survives intact — the excerpt is how the agent finds the
# element in its own TSX, so truncating mid-phrase makes a warning much harder to
# act on. The probe already caps what it sends at 80.
_TEXT_EXCERPT = 60

# Audits already running, keyed by video_id. Two concurrent audits of one video
# would stage into the same public directory and one would delete it from under
# the other — validate_job is deliberately not covered by the scene-work claim,
# so this is the guard. A second caller is skipped with a warning rather than
# blocked, since blocking a tool call for up to TEXT_AUDIT_TIMEOUT_SECS is worse
# than not auditing.
_audits_in_progress: set[str] = set()
_audit_lock = threading.Lock()

_DRIVER_REL = Path("audit") / "run-text-layout-audit.mjs"


# ── Frame planning (pure) ───────────────────────────────────────────────────

def _fade_out_frames(scene: dict) -> int:
    transition = scene.get("transitionToNext") or {}
    value = transition.get("durationInFrames")
    return DEFAULT_FADE_FRAMES if value is None else int(value)


def settled_window(scenes: list[dict], index: int) -> tuple[int, int, bool]:
    """Frame range of scene `index` with entrance and fade-out excluded.

    Returns (start, end, degenerate). `degenerate` is True when the scene is too
    short to have a settled window at all, in which case (start, end) collapses
    to its midpoint — a short scene still gets looked at, it just gets one
    sample and a note instead of being skipped silently.

    The fade arithmetic mirrors CompositionBuilder.tsx's: a scene's fade-IN
    length comes from the PREVIOUS scene's transitionToNext (they share the
    overlap window), its fade-OUT from its own, and the last scene has no
    fade-out. Keep in sync.
    """
    scene = scenes[index]
    start = int(scene.get("startFrame", 0))
    duration = int(scene.get("durationInFrames", 0))
    last_frame = start + max(0, duration - 1)

    prev = scenes[index - 1] if index > 0 else None
    fade_in = _fade_out_frames(prev) if prev is not None else 0
    fade_out = _fade_out_frames(scene) if index < len(scenes) - 1 else 0

    window_start = start + max(fade_in, ENTRANCE_ALLOWANCE_FRAMES)
    window_end = last_frame - fade_out

    if window_start > window_end:
        midpoint = start + max(0, duration // 2)
        return (midpoint, midpoint, True)
    return (window_start, window_end, False)


def plan_passes(scene_config: dict) -> tuple[list[dict], list[str]]:
    """Turn a scene-config into per-scene sampling instructions.

    Each pass is {scene, first, step, count} rather than an explicit frame list
    because that is exactly what Remotion samples: getFramesToRender keeps
    frames where (frame - frameRange[0]) % everyNthFrame == 0, i.e.
    first + k*step. Handing over an arbitrary list would mean the driver
    guessing a step that reproduces it.
    """
    scenes = scene_config.get("scenes") or []
    passes: list[dict] = []
    notes: list[str] = []

    for index, scene in enumerate(scenes):
        if int(scene.get("durationInFrames", 0)) <= 0:
            continue
        window_start, window_end, degenerate = settled_window(scenes, index)
        span = window_end - window_start
        if degenerate or span <= 0:
            count, step = 1, 1
            if degenerate:
                notes.append(
                    f"scene {index} ({_scene_label(scene)}) is too short for a settled "
                    f"window — sampled its midpoint (frame {window_start}) only"
                )
        else:
            count = min(SAMPLES_PER_SCENE, span + 1)
            step = max(1, span // max(1, count - 1))
            # Recompute count so first + step*(count-1) never runs past the
            # window; integer division can otherwise leave room for one more.
            count = min(count, span // step + 1)
        passes.append({
            "scene": index,
            "first": window_start,
            "step": step,
            "count": count,
        })

    return passes, notes


def _scene_label(scene: dict) -> str:
    if scene.get("type") == "TextReveal":
        return "TextReveal"
    return str(scene.get("src") or scene.get("type") or "?")


# ── Geometry (pure) ────────────────────────────────────────────────────────

def is_measurable(element: dict) -> bool:
    """Should this measured element take part in the overlap check?

    Rotated elements are excluded because getBoundingClientRect() returns the
    axis-aligned bounding box, which for rotated text is much larger than the
    glyphs — comparing those boxes would invent collisions. Nothing in the
    installed scenes or skill examples rotates text today; this is a guard
    against a future false-positive source, not a live case.
    """
    if element.get("rotated"):
        return False
    if float(element.get("opacity", 0)) < OPACITY_FLOOR:
        return False
    return float(element.get("width", 0)) > 0 and float(element.get("height", 0)) > 0


def _ink_box(element: dict) -> tuple[float, float, float, float]:
    """(x1, y1, x2, y2) of the element's measured text.

    No leading correction is applied, and this is deliberate. The probe measures
    a Range over the element's contents, not the element's box, and a Range rect
    is already tight to the glyph run: measured across five real elements it came
    back at 1.11-1.13x font-size while their CSS line-heights were 1.4-1.5x. An
    earlier version subtracted half-leading here, which was the right correction
    for element rects (CSS line boxes) and became a double-correction once the
    probe switched to Ranges — a 78px headline measuring 88px tall was being
    deflated to 49px, which loses real collisions.
    """
    x1 = float(element["x"])
    y1 = float(element["y"])
    return (x1, y1, x1 + float(element["width"]), y1 + float(element["height"]))


def overlap_fraction(a: dict, b: dict) -> float:
    """Intersection area as a fraction of the smaller element's area.

    Both boxes are the probe's glyph-tight Range rects, so this is an ink
    comparison rather than a line-box one.
    """
    ax1, ay1, ax2, ay2 = _ink_box(a)
    bx1, by1, bx2, by2 = _ink_box(b)

    overlap_w = min(ax2, bx2) - max(ax1, bx1)
    overlap_h = min(ay2, by2) - max(ay1, by1)
    if overlap_w <= 0 or overlap_h <= 0:
        return 0.0

    smaller = min((ax2 - ax1) * (ay2 - ay1), (bx2 - bx1) * (by2 - by1))
    if smaller <= 0:
        return 0.0
    return (overlap_w * overlap_h) / smaller


def _is_nested(a: dict, b: dict) -> bool:
    """Is one element an ancestor of the other?

    A parent's rect contains its child's, so such a pair always looks like a
    total overlap. The probe only reports leaf text elements, which makes this
    rare, but a mixed <div>text<span>more</span></div> could still produce one.
    """
    return (
        a["index"] in (b.get("ancestorIndices") or [])
        or b["index"] in (a.get("ancestorIndices") or [])
    )


def find_overlaps(elements: list[dict]) -> list[dict]:
    """Text-vs-text collisions among one frame's measured elements.

    TEXT-VS-TEXT ONLY, and that is not an arbitrary narrowing — it is what makes
    the check safe. ex-hybrid-anchored.tsx documents an arrow tip legitimately
    landing anywhere on the image, and an image layer routinely sits under the
    text drawn over it. Neither is text, so both are invisible to this check.
    Widening it to text-vs-any-element breaks both at once.
    """
    usable = [e for e in elements if is_measurable(e)]
    found: list[dict] = []
    for i, a in enumerate(usable):
        for b in usable[i + 1:]:
            if _is_nested(a, b):
                continue
            fraction = overlap_fraction(a, b)
            if fraction >= OVERLAP_MIN_FRACTION:
                found.append({"a": a, "b": b, "fraction": fraction})
    return found


def safe_zone_breaches(element: dict) -> list[str]:
    """Which safe-zone edges this element's text crosses, if any.

    Secondary to the overlap check, not the reason this ticket exists: the AI
    review was measured to handle safe-zone violations competently — it caught a
    real one quoting the correct 170px figure. What it also did was fabricate
    violations on two clean videos, and that is what an exact check fixes.

    TEXT ONLY. ex-hybrid-anchored.tsx documents an arrow TIP legitimately landing
    outside the zone, under the platform UI, while its label stays inside — so a
    HYBRID scene is audited, but only its label. Extending this to non-text
    elements would report that arrow as a defect on every anchored scene.

    Measured on the same glyph-tight box as the overlap check, so a line
    box's padding cannot push text over an edge it does not actually cross.
    """
    x1, y1, x2, y2 = _ink_box(element)
    tol = SAFE_ZONE_TOLERANCE_PX
    breaches = []
    if x1 < SAFE_ZONE["left"] - tol:
        breaches.append(f"left (x={x1:.0f} < {SAFE_ZONE['left']})")
    if x2 > FRAME_WIDTH - SAFE_ZONE["right"] + tol:
        breaches.append(f"right (x={x2:.0f} > {FRAME_WIDTH - SAFE_ZONE['right']})")
    if y1 < SAFE_ZONE["top"] - tol:
        breaches.append(f"top (y={y1:.0f} < {SAFE_ZONE['top']})")
    if y2 > FRAME_HEIGHT - SAFE_ZONE["bottom"] + tol:
        breaches.append(f"bottom (y={y2:.0f} > {FRAME_HEIGHT - SAFE_ZONE['bottom']})")
    return breaches


def is_clipped(element: dict) -> bool:
    """Does the element run past the frame itself, not just the safe zone?

    Strictly worse than a safe-zone breach — this text is cut off rather than
    merely sitting under the platform UI, and it is the `text_offscreen` case.
    """
    x1, y1, x2, y2 = _ink_box(element)
    tol = SAFE_ZONE_TOLERANCE_PX
    return (
        x1 < -tol or y1 < -tol
        or x2 > FRAME_WIDTH + tol or y2 > FRAME_HEIGHT + tol
    )


def find_safe_zone_violations(elements: list[dict]) -> list[dict]:
    """Safe-zone breaches among one frame's measured elements."""
    found: list[dict] = []
    for element in elements:
        if not is_measurable(element):
            continue
        breaches = safe_zone_breaches(element)
        if breaches:
            found.append({
                "element": element,
                "breaches": breaches,
                "clipped": is_clipped(element),
            })
    return found


# ── Reporting ──────────────────────────────────────────────────────────────

def _excerpt(element: dict) -> str:
    text = (element.get("text") or "").strip()
    return text[:_TEXT_EXCERPT] if len(text) <= _TEXT_EXCERPT else text[:_TEXT_EXCERPT] + "…"


def _pair_key(scene: int, a: dict, b: dict) -> tuple:
    return (scene, *sorted((_excerpt(a), _excerpt(b))))


def summarise(driver_output: dict, scene_config: dict) -> list[str]:
    """Collapse per-frame measurements into one warning per colliding pair.

    A collision normally shows up at every sampled frame of a scene; reporting
    it once, at whichever frame it was worst, keeps the warning list actionable.
    """
    scenes = scene_config.get("scenes") or []
    worst: dict[tuple, dict] = {}
    zones: dict[tuple, dict] = {}

    for pass_result in driver_output.get("passes") or []:
        scene_index = pass_result.get("scene")
        for frame_result in pass_result.get("frames") or []:
            frame = frame_result.get("frame")
            elements = frame_result.get("elements") or []
            for hit in find_overlaps(elements):
                key = _pair_key(scene_index, hit["a"], hit["b"])
                if key not in worst or hit["fraction"] > worst[key]["fraction"]:
                    worst[key] = {**hit, "scene": scene_index, "frame": frame}
            for hit in find_safe_zone_violations(elements):
                key = (scene_index, _excerpt(hit["element"]), tuple(hit["breaches"]))
                if key not in zones:
                    zones[key] = {**hit, "scene": scene_index, "frame": frame}

    warnings: list[str] = []
    for hit in sorted(worst.values(), key=lambda h: -h["fraction"]):
        scene = scenes[hit["scene"]] if hit["scene"] < len(scenes) else {}
        a, b = hit["a"], hit["b"]
        warnings.append(
            f"Text overlap in scene {hit['scene']} ({_scene_label(scene)}) at frame "
            f"{hit['frame']}: '{_excerpt(a)}' "
            f"[{a['x']:.0f},{a['y']:.0f} {a['width']:.0f}x{a['height']:.0f}] overlaps "
            f"'{_excerpt(b)}' "
            f"[{b['x']:.0f},{b['y']:.0f} {b['width']:.0f}x{b['height']:.0f}] "
            f"by {hit['fraction'] * 100:.0f}% of the smaller box"
        )

    for hit in zones.values():
        scene = scenes[hit["scene"]] if hit["scene"] < len(scenes) else {}
        element = hit["element"]
        clipped = " and is CLIPPED by the frame edge" if hit["clipped"] else ""
        warnings.append(
            f"Text outside the safe zone in scene {hit['scene']} "
            f"({_scene_label(scene)}) at frame {hit['frame']}: '{_excerpt(element)}' "
            f"crosses {', '.join(hit['breaches'])}{clipped}"
        )

    for pass_result in driver_output.get("passes") or []:
        requested = pass_result.get("requestedFrames") or []
        measured = {f.get("frame") for f in pass_result.get("frames") or []}
        missing = [f for f in requested if f not in measured]
        if missing:
            warnings.append(
                f"Text-layout audit could not measure scene {pass_result.get('scene')} at "
                f"frame(s) {missing} — that part of the scene was not checked"
            )

    for err in driver_output.get("errors") or []:
        warnings.append(f"Text-layout audit problem: {err}")

    return warnings


# ── Staging + execution ────────────────────────────────────────────────────

def _stage(video_id: str, remotion_dir: Path, scene_config_path: Path,
           timeline_path: Path, audio_path: Path) -> Path:
    """Copy a video's job files where the audit composition can fetch them.

    Mirrors renderer/api/worker.py's staging step. Not optional: the composition
    fetches /public/<vid>/scene-config.json, and an <Img> whose src does not
    resolve calls cancelRender() after two retries, which would kill the audit
    render outright rather than degrade.

    The directory name is fixed to video_id (not made unique per call) because
    image srcs are baked into scene-config.json as /public/<vid>/images/... —
    concurrency is handled by _audits_in_progress instead.

    The three paths come from validate_job, which derives them from the id
    (tubematic_core.jobfiles), so images/ beside the scene config is the
    video's own. A symlinked images/ is refused and symlinks inside it are
    skipped: copytree follows them, which would copy any file the server can
    read into the served tree.
    """
    public_dir = remotion_dir / "public" / video_id
    public_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy(scene_config_path, public_dir / tjobs.SCENE_CONFIG)
    shutil.copy(timeline_path, public_dir / tjobs.TIMELINE)
    shutil.copy(audio_path, public_dir / tjobs.AUDIO)

    images_dir = scene_config_path.parent / tjobs.IMAGES
    if images_dir.is_dir() and not images_dir.is_symlink():
        shutil.copytree(images_dir, public_dir / tjobs.IMAGES, dirs_exist_ok=True,
                        ignore=tjobs.ignore_symlinks)
    return public_dir


def _run_driver(remotion_dir: Path, config: dict) -> dict:
    """Run the Node driver and parse its JSON. Raises RuntimeError on failure.

    The driver writes its result to a file rather than stdout. Remotion forwards
    every browser console line to stdout, and the probe reports its measurements
    *as* console logs, so this subprocess's stdout always carries the probe's own
    chatter. Parsing stdout looked fine in unit tests (which hand the parsed dict
    straight to summarise) and failed on the very first real in-container run.
    """
    node_bin = shutil.which("node")
    if not node_bin:
        raise RuntimeError("node not found on PATH")
    driver = remotion_dir / _DRIVER_REL
    if not driver.is_file():
        raise RuntimeError(f"audit driver missing: {driver}")

    out_fd, out_name = tempfile.mkstemp(prefix="tubematic-text-audit-", suffix=".json")
    os.close(out_fd)
    out_path = Path(out_name)
    config = {**config, "outputPath": out_name}

    # start_new_session + killpg: a plain
    # subprocess.run(timeout=) kills only the direct child, orphaning the
    # Chromium and node processes it spawned.
    #
    # Deliberately NO wildcard os.waitpid(-1, ...) reap loop here, even though
    # worker.py's render timeout has one. That is safe there because worker.py is
    # a single-threaded poll loop with one subprocess in flight; this module runs
    # inside a multi-threaded MCP server where other calls also shell out
    # (validate_job's tsc, a concurrent audit), and a wildcard reap can claim a
    # different call's child out from under it. killpg alone is sufficient: it
    # SIGKILLs the whole group synchronously.
    proc = subprocess.Popen(
        [node_bin, str(_DRIVER_REL), json.dumps(config)],
        cwd=str(remotion_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        start_new_session=True,
    )
    try:
        try:
            stdout, stderr = proc.communicate(timeout=TEXT_AUDIT_TIMEOUT_SECS)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.wait()
            raise RuntimeError(f"timed out after {TEXT_AUDIT_TIMEOUT_SECS}s")

        # The result file is the real channel. If it has content, it is the
        # driver's own document and a parse failure there is worth reporting
        # verbatim.
        raw = out_path.read_text() if out_path.is_file() else ""
        if raw.strip():
            try:
                return json.loads(raw)
            except json.JSONDecodeError as e:
                raise RuntimeError(f"driver output was not JSON: {e}")

        # No file: either the driver rejected the config before it learned
        # outputPath (it falls back to stdout for exactly that case), or it died
        # early. Only accept stdout if it actually parses — otherwise it is
        # Remotion's console/progress chatter, and the stderr tail says far more
        # about what went wrong.
        stdout_s = (stdout or "").strip()
        if stdout_s:
            try:
                return json.loads(stdout_s)
            except json.JSONDecodeError:
                pass

        detail = (stderr or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit {proc.returncode}, no output"
        raise RuntimeError(tail)
    finally:
        out_path.unlink(missing_ok=True)


def audit_text_layout(video_id: str, scene_config: dict, scene_config_path: Path,
                      timeline_path: Path, audio_path: Path,
                      remotion_dir: Path) -> list[str]:
    """Audit one video's text layout. Returns advisory warning lines.

    FAILS OPEN on every failure mode — a broken audit reports that it could not
    run and nothing else. It must never be able to block a render, which is the
    same house style validate_job's tsc block already follows.
    """
    with _audit_lock:
        if video_id in _audits_in_progress:
            return [f"Text-layout audit skipped: an audit for {video_id} is already running"]
        _audits_in_progress.add(video_id)

    public_dir = None
    try:
        passes, notes = plan_passes(scene_config)
        if not passes:
            return notes

        public_dir = _stage(video_id, remotion_dir, scene_config_path,
                            timeline_path, audio_path)
        output = _run_driver(remotion_dir, {
            "sceneConfigPath": f"/public/{video_id}/scene-config.json",
            "timelinePath": f"/public/{video_id}/timeline.json",
            "audioPath": f"/public/{video_id}/audio.mp3",
            "passes": passes,
            "browserExecutable": os.getenv("PUPPETEER_EXECUTABLE_PATH") or None,
        })
        return notes + summarise(output, scene_config)
    except Exception as e:
        return [f"Text-layout audit could not run ({e}) — text layout was not checked"]
    finally:
        if public_dir is not None:
            shutil.rmtree(public_dir, ignore_errors=True)
        with _audit_lock:
            _audits_in_progress.discard(video_id)
