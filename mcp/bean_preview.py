"""Renders the preview of the props an agent drew for one Bean Explainer video
(TMDEV-198): the picture render_bean_props hands back so the agent sees its
drawings before it submits.

The renderer is the Node script renderer/remotion/bean-tools/render-props.mjs,
run as `node render-props.mjs <spec_json> <out_png>`. It runs on software GL
inside this server's container, so the GPU stays free for videos. Success is
exit 0 AND the PNG existing.

Stdlib only: server.py imports it beside mascot_sheets.
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import tempfile
from pathlib import Path

_SCRIPT = Path("bean-tools") / "render-props.mjs"
STDERR_TAIL_LINES = 8
# Under server.py's HEAVY_CHECK_WAIT_SECS (300): the preview holds the heavy-check
# lock, and a validate_job queued behind it must not give up first.
TIMEOUT_SECS = 240


class BeanPreviewError(Exception):
    """The preview could not be rendered. The message is for the authoring agent."""


def render_preview(remotion_dir, spec: dict, out_png, timeout: int = TIMEOUT_SECS) -> None:
    remotion_dir, out_png = Path(remotion_dir), Path(out_png)
    script = remotion_dir / _SCRIPT
    if not script.is_file():
        raise BeanPreviewError(f"the preview renderer is missing: {script}")
    node = shutil.which("node")
    if not node:
        raise BeanPreviewError("node was not found on PATH")
    # A picture left by an earlier render must never pass for this one.
    out_png.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="tubematic-bean-preview-") as tmp:
        spec_file = Path(tmp) / "spec.json"
        spec_file.write_text(json.dumps(spec), encoding="utf-8")
        # New session + killpg, not subprocess.run(timeout=): that kills only node
        # and orphans the Chromium it started. No wildcard waitpid reap: this
        # server is multi-threaded (see mascot_sheets.render_sheet).
        proc = subprocess.Popen(
            [node, str(script), str(spec_file), str(out_png)],
            cwd=str(remotion_dir), env=dict(os.environ),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        try:
            _, stderr = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            proc.communicate()
            out_png.unlink(missing_ok=True)
            raise BeanPreviewError(f"the preview did not finish within {timeout} s") from None
    if proc.returncode != 0:
        tail = "\n".join((stderr or "").strip().splitlines()[-STDERR_TAIL_LINES:])
        raise BeanPreviewError(f"the preview failed to render (exit {proc.returncode}): {tail or 'no error output'}")
    if not out_png.is_file():
        raise BeanPreviewError("the preview renderer finished but wrote no image")
