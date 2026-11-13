"""The preview_frames tool's work: frames of a video's composed scene as the
render will draw them (TMDEV-241).

A video's main style, inserts, captions, mascot and watermark are all drawn
by the one Composition, so the frames come from the same command line the
Cartoon 3D stills use (cartoon-tools/dist/still.mjs). It renders the real
Composition with the props this module builds, through the built-in
renderer's stills server (on the GPU when there is one) or, when none
answers, on this container's CPU. Nothing here judges the pictures: the agent
looks at them and fixes what it sees.

The props equal the render's (renderer/api/render_agent.py's render_props):
the three job-file paths, the watermark from the settings table, and, for a
video that has a mascot, the pinned mascot code staged beside the previews. The pictures are written only under <video>/preview/, the one
folder besides cartoon/ that the stills server accepts (out-path.mjs).

Cartoon 3D keeps its own tools (cartoon_still), which know its source tree
and its beat gate; a Cartoon 3D video is sent there.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import cartoon
from tubematic_core import jobfiles as tjobs

PREVIEW_DIR = "preview"
MASCOT_FILE = "mascot.js"
MAX_FRAMES_PER_CALL = 6
TIMEOUT_SECS = 600
_PNG_RE = re.compile(r"^f\d{4,}\.png$")


class PreviewError(Exception):
    """A refusal with a reason the agent can act on."""


def _total_frames(timeline_path: Path) -> int:
    try:
        total = json.loads(timeline_path.read_text(encoding="utf-8")).get("totalFrames")
    except (OSError, ValueError, AttributeError):
        raise PreviewError("timeline.json cannot be read: call get_timeline to see what generate_voice wrote")
    if isinstance(total, bool) or not isinstance(total, int) or total < 1:
        raise PreviewError("timeline.json has no totalFrames")
    return total


def _check_frames(frames, total: int) -> list[int]:
    if (not isinstance(frames, list) or not 1 <= len(frames) <= MAX_FRAMES_PER_CALL
            or any(isinstance(f, bool) or not isinstance(f, int) or f < 0 for f in frames)):
        raise PreviewError(f"frames must list 1 to {MAX_FRAMES_PER_CALL} whole frame numbers, none negative")
    if any(f >= total for f in frames):
        raise PreviewError(f"the video has {total} frames (0 to {total - 1}); frames must lie inside it")
    return list(frames)


def _clear(folder: Path) -> None:
    """The previous call's pictures and mascot file; nothing else in the folder.
    A symlink under one of those names is removed itself (unlink never follows
    it), so the mascot file is never written through a planted link."""
    if not folder.is_dir():
        return
    for p in folder.iterdir():
        if (p.is_file() or p.is_symlink()) and (p.name == MASCOT_FILE or _PNG_RE.match(p.name)):
            p.unlink()


def preview(jobs_dir, video_id: str, remotion_dir: Path, frames, *, watermark: bool,
            mascot_code: str | None) -> list[Path]:
    """Draw `frames`, returning the PNG paths in the order asked. `mascot_code`
    is the pinned version's drawing code of the video's mascot (None for a video
    without one). Raises PreviewError."""
    try:
        config_path, timeline_path, _audio = cartoon._job_files(jobs_dir, video_id)
        folder = cartoon._below(jobs_dir, video_id, PREVIEW_DIR)
    except (cartoon.CartoonError, tjobs.UnsafePath) as e:
        raise PreviewError(str(e))
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except ValueError as e:
        raise PreviewError(f"scene-config.json is not valid JSON: {e}")
    if cartoon.is_cartoon(config):
        raise PreviewError("this is a Cartoon 3D video: look at it with cartoon_still (and cartoon_read_still), "
                           "which render its world from its own source")
    clean = _check_frames(frames, _total_frames(timeline_path))

    lock = cartoon._lock_for(video_id)
    if not lock.acquire(blocking=False):
        raise PreviewError(f"another preview or Cartoon 3D tool is still running for {video_id}; wait for it")
    try:
        _clear(folder)
        props = cartoon._props(video_id)
        props["watermark"] = bool(watermark)
        if mascot_code:
            try:
                folder.mkdir(parents=True, exist_ok=True)
                # exclusive and never through a link: a name left by anything else is a refusal
                fd = os.open(folder / MASCOT_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(mascot_code)
            except OSError as e:
                raise PreviewError(f"the mascot's code could not be staged in {PREVIEW_DIR}/: {e.strerror or e}")
            props["mascotPath"] = f"/public/{video_id}/{PREVIEW_DIR}/{MASCOT_FILE}"
        try:
            proc = cartoon.run_cli(remotion_dir, "still", [str(tjobs.job_dir(jobs_dir, video_id)), str(folder), *map(str, clean)],
                                   timeout=TIMEOUT_SECS, props=props, public_dir=Path(jobs_dir))
        except cartoon.CartoonError as e:
            raise PreviewError(str(e))
        if proc.returncode != 0:
            text = cartoon._fail_text(proc)
            if "is not under" in text:
                raise PreviewError("the renderer is older than this tool and refuses the preview folder: finish "
                                   "upgrading the renderer, and carry on without a preview until then")
            raise PreviewError(f"the frames could not be rendered: {text}")
        try:
            drawn = [Path(p) for p in cartoon._last_json(proc.stdout).get("stills", [])]
        except cartoon.CartoonError as e:
            raise PreviewError(str(e))
        return drawn
    finally:
        lock.release()
