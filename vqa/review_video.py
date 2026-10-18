#!/usr/bin/env python3
"""On-demand Gemini quality review for an already-rendered VQA video.

Usage: review_video.py <video_id>

Finds the rendered mp4 and scene-config.json from the video's id and project
(tubematic_core.jobfiles, the same derivation the worker and the API use) under
the host data root, then calls the same pure run_ai_review() the render worker
uses (renderer/api/ai_review.py). The stored path columns only say whether each
file was written: they were once writable by any caller, so a row could name
any host file to be uploaded for review.

Deliberately does NOT write videos.gemini_feedback, add a comment, bump
ai_review_count, or touch status — unlike the worker's automatic post-render
review, which does all four and can route the video to REVISION_REQUESTED.
That's the whole point of this being a standalone script instead of a call
into the worker's review path: re-reviewing the same video any number of
times is free of side effects. See vqa/README.md for the on-demand-review
design rationale (VQA seeds gemini_review_enabled=false for the same reason).

The feedback is also written to mounted/jobs/<video_id>/ai_review.txt —
overwritten on each re-run, so the file always reflects the most recent
review (same convention as vqa/stage_script.py's two files).

Runtime note: a review can take up to ~7 minutes worst case (Gemini's upload
poll loop is bounded at 60 x 5s, plus up to 120s for the review call itself).
"""
import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

# The shared package lives at the repo root; this script runs with only its own
# directory on sys.path. Same guard as renderer/api/pipeline.py.
try:
    from tubematic_core import jobfiles as tjobs
except ModuleNotFoundError:  # pragma: no cover - the normal host-side case
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tubematic_core import jobfiles as tjobs

# Fallbacks for when the settings rows are absent, which is the normal case
# here: vqa/make_seed_db.py deliberately seeds only the keys that differ from
# SETTINGS_SPEC's defaults. These must match those defaults (and worker.py's
# own `_setting` fallbacks) or /vqa-review would sample a video differently
# from the pipeline it exists to assess. Keep in sync with
# renderer/api/pipeline.py's SETTINGS_SPEC.
_DEFAULT_REVIEW_MODEL = "gemini-2.5-flash"
_DEFAULT_REVIEW_FPS = "10"


def _repo_root() -> Path:
    """This script's own location determines where ai_review.py lives
    (renderer/api/, a fixed sibling directory) — resolving from __file__
    rather than cwd means it works the same whether invoked directly or via
    the /vqa-review slash command's absolute path."""
    return Path(__file__).resolve().parent.parent


def _data_root() -> Path:
    """Where pipeline data lives — a fixed absolute path (TMDEV-76), distinct
    from the repo root above, which still locates importable source. A VQA
    session therefore reads the same tree the containers write to, wherever
    the checkout happens to sit."""
    return Path.home() / ".tubematic-data"


def review_video(video_id: str, root: Path, run_review=None) -> tuple[str, Path]:
    """Return (feedback, review_path) for video_id. Makes no DB writes — the
    only file this touches is review_path itself
    (mounted/jobs/<video_id>/ai_review.txt), which it overwrites with the
    feedback on every call.

    run_review defaults to ai_review.run_ai_review, imported from this
    script's own renderer/api/ sibling — injectable so callers (tests) can
    swap in a fake reviewer without needing a live Gemini key or a full
    renderer/api/ tree under an arbitrary `root`. It is called with
    run_ai_review's full signature, including the keyword-only script_text /
    tts_text pronunciation reference.
    """
    db_path = root / "data" / "tubematic.db"
    if not db_path.exists():
        raise SystemExit(f"No database at {db_path} — has the VQA stack been bootstrapped?")

    con = sqlite3.connect(str(db_path))
    try:
        row = con.execute(
            "SELECT video_path, scene_config_path, status, script, tts_text, project_id"
            " FROM videos WHERE id = ?",
            (video_id,),
        ).fetchone()
        # VQA-7: the review model and sampling rate are settings-table values
        # read by the worker and passed into run_ai_review (ai_review.py is
        # deliberately DB-free). Read them here too, or /vqa-review would
        # silently review on different settings than the pipeline does — which
        # would make any before/after comparison run through this script
        # meaningless.
        settings = dict(con.execute(
            "SELECT key, value FROM settings WHERE key IN "
            "('ai_review_model', 'ai_review_fps', 'gemini_api_key')"
        ).fetchall())
    finally:
        con.close()

    if row is None:
        raise SystemExit(f"No video found with id {video_id!r}")
    video_path, scene_config_path, status, script_text, tts_text, project_id = row
    if not video_path:
        raise SystemExit(f"Video {video_id} has not been rendered yet (current status: {status})")
    if not scene_config_path:
        raise SystemExit(
            f"Video {video_id} has no scene_config_path recorded (current status: {status})"
        )

    output_videos_dir = Path(os.environ.get("OUTPUT_VIDEOS_PATH") or (root / "output_videos"))
    try:
        host_video_path = tjobs.output_file(output_videos_dir, project_id, video_id)
        host_scene_config_path = tjobs.job_file(root / "jobs", video_id, tjobs.SCENE_CONFIG)
    except tjobs.UnsafePath as e:
        raise SystemExit(f"Refusing to review {video_id}: {e}")

    if not host_video_path.is_file():
        raise SystemExit(f"Rendered video not found on disk at {host_video_path}")
    if not host_scene_config_path.is_file():
        raise SystemExit(f"scene-config.json not found on disk at {host_scene_config_path}")

    scene_config = json.loads(host_scene_config_path.read_text())

    if run_review is None:
        sys.path.insert(0, str(_repo_root() / "renderer" / "api"))
        from ai_review import run_ai_review as run_review  # noqa: E402

    # VQA-6: the pronunciation reference — the authored wording (captions) and
    # the exact text ElevenLabs was given. Passing them is what keeps a
    # deliberate <respell> substitution from being reported as a defect.
    result = run_review(str(host_video_path), scene_config,
                        script_text=script_text or "", tts_text=tts_text or "",
                        model=settings.get("ai_review_model", _DEFAULT_REVIEW_MODEL),
                        fps=settings.get("ai_review_fps", _DEFAULT_REVIEW_FPS),
                        api_key=settings.get("gemini_api_key", "")
                                 or os.environ.get("GEMINI_API_KEY", ""))
    feedback = result["feedback"]

    job_dir = root / "jobs" / video_id
    job_dir.mkdir(parents=True, exist_ok=True)
    review_path = job_dir / "ai_review.txt"
    review_path.write_text(feedback.strip() + "\n")

    return feedback, review_path


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    args = parser.parse_args(argv)

    root = _data_root()
    print(f"Reviewing {args.video_id} — this can take several minutes...", file=sys.stderr)
    feedback, review_path = review_video(args.video_id, root)
    print(feedback)
    print(f"\nWritten to: {review_path}")


if __name__ == "__main__":
    main()
