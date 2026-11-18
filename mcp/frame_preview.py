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

import hashlib
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import cartoon
from tubematic_core import external_styles
from tubematic_core import jobfiles as tjobs

PREVIEW_DIR = "preview"
MASCOT_FILE = "mascot.js"
RECORD_FILE = "record.json"
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


def _content_hash(config_path: Path, timeline_path: Path) -> str:
    """What a look was taken of: the scene-config and the timeline, and for a
    video in an external style (TMDEV-252) the package's fingerprint, since an
    updated package draws a different picture from the same config."""
    h = hashlib.sha256()
    for p in (config_path, timeline_path):
        h.update(p.read_bytes())
        h.update(b"\0")
    try:
        style = external_styles.config_style(json.loads(config_path.read_text(encoding="utf-8")))
    except ValueError:
        style = ""
    if style:
        try:
            h.update(external_styles.fingerprint(style).encode())
        except (OSError, tjobs.UnsafePath):
            h.update(b"no package")
    return h.hexdigest()


def _open_folder(folder: Path) -> int:
    """A handle on the preview folder, made if it is missing, never following a link: the folder is
    created with a plain mkdir (which refuses an existing link, dangling or not) and opened with
    O_NOFOLLOW. Raises OSError."""
    try:
        return os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        try:
            os.mkdir(folder)
        except FileExistsError:
            pass
        return os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)


def _write_record(folder: Path, sha: str, status: str, frames: list[int], why: str = "") -> None:
    """preview/record.json: which scene-config and timeline were looked at, and whether the
    frames drew ("ok") or the tool itself could not ("unavailable"). Written beside a folder
    handle opened without following a link, to a new name and renamed into place."""
    try:
        dir_fd = _open_folder(folder)
        try:
            tmp = RECORD_FILE + ".tmp"
            try:
                os.unlink(tmp, dir_fd=dir_fd)
            except FileNotFoundError:
                pass
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dir_fd)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"sha": sha, "status": status, "frames": frames, "why": why[:500],
                           "at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}, fh)
            os.replace(tmp, RECORD_FILE, src_dir_fd=dir_fd, dst_dir_fd=dir_fd)
        finally:
            os.close(dir_fd)
    except OSError:
        pass   # no record means the submit asks for a look again; nothing here may fail the call


def look_recorded(jobs_dir, video_id: str) -> bool:
    """Whether the scene-config and timeline as they are now were looked at: a record of
    this exact content, "ok" or "unavailable". What submit_render asks for."""
    try:
        config_path, timeline_path, _audio = cartoon._job_files(jobs_dir, video_id)
        folder = cartoon._below(jobs_dir, video_id, PREVIEW_DIR)
        sha = _content_hash(config_path, timeline_path)
        dir_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            fd = os.open(RECORD_FILE, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=dir_fd)
        finally:
            os.close(dir_fd)
        with os.fdopen(fd, "r", encoding="utf-8") as fh:
            rec = json.load(fh)
    except (OSError, ValueError, cartoon.CartoonError, tjobs.UnsafePath):
        return False
    return isinstance(rec, dict) and rec.get("sha") == sha and rec.get("status") in ("ok", "unavailable")


def _clear(folder: Path) -> None:
    """The previous call's pictures and mascot file; nothing else in the folder.
    The folder is opened without following a link and its entries removed
    beside that handle, so a folder swapped for a link is never followed, and
    a link under one of those names is removed itself (unlink never follows it)."""
    try:
        dir_fd = os.open(folder, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    except FileNotFoundError:
        return
    except OSError as e:
        raise PreviewError(f"{PREVIEW_DIR}/ cannot be cleared: {e.strerror or e}")
    try:
        with os.scandir(dir_fd) as entries:
            names = [e.name for e in entries
                     if (e.name == MASCOT_FILE or _PNG_RE.match(e.name)) and (e.is_symlink() or e.is_file(follow_symlinks=False))]
        for name in names:
            os.unlink(name, dir_fd=dir_fd)
    finally:
        os.close(dir_fd)


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
        sha = _content_hash(config_path, timeline_path)
        _clear(folder)
        props = cartoon._props(video_id)
        props["watermark"] = bool(watermark)
        if mascot_code:
            try:
                # exclusive and never through a link: a name left by anything else is a refusal. The folder is
                # opened without following a link and the file made beside that handle, so a folder swapped
                # for a link after the check above is not followed either
                dir_fd = _open_folder(folder)
                try:
                    fd = os.open(MASCOT_FILE, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o644, dir_fd=dir_fd)
                finally:
                    os.close(dir_fd)
                with os.fdopen(fd, "w", encoding="utf-8") as fh:
                    fh.write(mascot_code)
            except OSError as e:
                raise PreviewError(f"the mascot's code could not be staged in {PREVIEW_DIR}/: {e.strerror or e}")
            props["mascotPath"] = f"/public/{video_id}/{PREVIEW_DIR}/{MASCOT_FILE}"
        why = ""
        try:
            try:
                proc = cartoon.run_cli(remotion_dir, "still", [str(tjobs.job_dir(jobs_dir, video_id)), str(folder), *map(str, clean)],
                                       timeout=TIMEOUT_SECS, props=props, public_dir=Path(jobs_dir),
                                       external_style=external_styles.config_style(config), video_id=video_id)
            except (cartoon.CartoonError, OSError, subprocess.SubprocessError) as e:
                why = str(e) or e.__class__.__name__
                raise PreviewError(why)
            if proc.returncode != 0:
                text = cartoon._fail_text(proc)
                if "is not under" in text:
                    why = ("the renderer is older than this tool and refuses the preview folder: finish "
                           "upgrading the renderer, and carry on without a preview until then")
                else:
                    why = f"the frames could not be rendered: {text}"
                raise PreviewError(why)
            try:
                stills = cartoon._last_json(proc.stdout).get("stills", [])
                if not isinstance(stills, list) or not all(isinstance(p, str) for p in stills):
                    raise cartoon.CartoonError("the renderer's answer did not list the pictures it drew")
                drawn = [Path(p) for p in stills]
            except (cartoon.CartoonError, AttributeError) as e:
                why = str(e) or "the renderer's answer was not understood"
                raise PreviewError(why)
        except PreviewError:
            _write_record(folder, sha, "unavailable", clean, why)
            raise
        _write_record(folder, sha, "ok", clean)
        return drawn
    finally:
        lock.release()
