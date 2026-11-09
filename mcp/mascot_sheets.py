"""Renders one model sheet of a mascot: the picture a human reviews.

The renderer is the Node script renderer/remotion/mascot-tools/render-sheet.mjs,
run as `node render-sheet.mjs <code_file> <sheet> <out_png>`: it draws the
mascot's code on the MascotSheet composition (the `turn`, `feels` and `act`
sheets) and writes a PNG. It runs on software GL, inside this server's
container, so the GPU stays free for videos. Success is exit 0 AND the PNG
existing: a renderer that exits 0 without a picture is a failure.

Stdlib only: server.py imports it beside text_audit and cartoon.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
from pathlib import Path

_SCRIPT = Path("mascot-tools") / "render-sheet.mjs"
STDERR_TAIL_LINES = 8


class MascotSheetError(Exception):
    """The sheet could not be rendered. The message is for the authoring agent."""


def render_sheet(remotion_dir, code_file, sheet, out_png, timeout=1200) -> None:
    remotion_dir, out_png = Path(remotion_dir), Path(out_png)
    script = remotion_dir / _SCRIPT
    if not script.is_file():
        raise MascotSheetError(f"the sheet renderer is missing: {script}")
    node = shutil.which("node")
    if not node:
        raise MascotSheetError("node was not found on PATH")
    # A picture left by an earlier render must never pass for this one.
    out_png.unlink(missing_ok=True)
    # New session + killpg, not subprocess.run(timeout=): that kills only node and
    # orphans the Chromium it started. No wildcard waitpid reap here (see
    # text_audit._run_driver): this server is multi-threaded.
    proc = subprocess.Popen(
        [node, str(script), str(code_file), sheet, str(out_png)],
        cwd=str(remotion_dir), env=dict(os.environ),
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
    )
    try:
        _, stderr = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        proc.communicate()
        out_png.unlink(missing_ok=True)
        raise MascotSheetError(f"the {sheet} sheet did not finish within {timeout} s") from None
    if proc.returncode != 0:
        tail = "\n".join((stderr or "").strip().splitlines()[-STDERR_TAIL_LINES:])
        raise MascotSheetError(f"the {sheet} sheet failed to render (exit {proc.returncode}): "
                               f"{tail or 'no error output'}")
    if not out_png.is_file():
        raise MascotSheetError(f"the {sheet} sheet renderer finished but wrote no image")
