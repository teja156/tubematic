#!/usr/bin/env python3
"""Stage the generated script as plain-text files for human review.

Writes two files to mounted/jobs/<video_id>/:

  script_with_broll.txt — every segment's spoken text next to its
                           visual/b-roll direction, straight from
                           videos.script_segments.
  tts_text.txt           — the text that would actually be sent to
                           ElevenLabs: segments joined, then the exact
                           phoneme/respell/lexicon processing
                           generate_voice() applies — reusing its private
                           helpers from mcp/server.py rather than a second,
                           drift-prone copy of that logic.

Needs only videos.script_segments to exist — not an actual voicing call — so
/vqa-new-video runs this at the SCRIPT_READY checkpoint, before the human
approves the (non-refundable) ElevenLabs spend, not after. tts_text.txt is
therefore a *preview* of what generate_voice() would send under the
*current* settings, not a captured copy of literal bytes already sent — it
can only go stale if settings.pronunciation_lexicon, the video's voice, or
that voice's model change between staging and actually voicing.
Re-run after a script revision (or a settings change) to refresh it.

Usage: stage_script.py <video_id>
"""
import argparse
import os
import sys
from pathlib import Path

# The shared package lives at the repo root; this script runs with only its own
# directory on sys.path. Same guard as vqa/review_video.py.
try:
    from tubematic_core import jobfiles as tjobs
except ModuleNotFoundError:  # pragma: no cover - the normal host-side case
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from tubematic_core import jobfiles as tjobs


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _data_root() -> Path:
    """Where pipeline data lives — a fixed absolute path (TMDEV-76), distinct
    from the repo root above, which still locates importable source. A VQA
    session therefore reads the same tree the containers write to, wherever
    the checkout happens to sit."""
    return Path.home() / ".tubematic-data"


def _import_mcp_server(root: Path):
    """Import mcp/server.py, pointed at this working tree's DB. DB_FILE is a
    module-level constant computed from TUBEMATIC_DB at import time, so the
    env var has to be set first. setdefault (not plain assignment) so a
    caller's own override — e.g. a test pointing at a temp DB — always wins
    over this default."""
    os.environ.setdefault("TUBEMATIC_DB", str(root / "data" / "tubematic.db"))
    os.environ.setdefault("TUBEMATIC_JOBS_DIR", str(root / "jobs"))
    sys.path.insert(0, str(_repo_root() / "mcp"))
    import server as mcp_server  # noqa: E402
    return mcp_server


def _format_broll(segments: list[dict]) -> str:
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(f"--- Segment {i} (id: {seg['id']}) ---")
        lines.append(f"VOICE:  {seg['voice'].strip()}")
        lines.append(f"VISUAL: {seg['visual'].strip() or '(none)'}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def stage_script(video_id: str, root: Path, mcp_server=None) -> tuple[Path, Path]:
    """Write script_with_broll.txt and tts_text.txt for video_id. Returns
    (broll_path, tts_path). mcp_server is injectable for testing (a fake
    exposing the same private-function surface); defaults to importing the
    real mcp/server.py."""
    if mcp_server is None:
        mcp_server = _import_mcp_server(root)

    with mcp_server._conn() as con:
        video = mcp_server._fetch_video(con, video_id)
    if not video:
        raise SystemExit(f"No video found with id {video_id!r}")

    segments = video.get("script_segments")
    if not segments:
        raise SystemExit(
            f"Video {video_id} has no script_segments yet (current status: "
            f"{video['status']}) — nothing to stage until scripting is done."
        )

    # The model is the video's voice's own (TMDEV-121), resolved exactly as
    # generate_voice resolves it.
    voice = mcp_server._resolve_voice(video.get("voice_id") or "")
    if voice is None:
        raise SystemExit(f"Video {video_id} has no voice in the roster — set a default voice "
                         "(vqa/edit_settings.py) or give the video one.")
    model_id, label = voice["model_id"], voice["name"]
    mode = mcp_server._pronunciation_mode_for_model(model_id)
    lexicon = mcp_server._get_lexicon()

    joined = mcp_server._join_segment_voice(segments)
    # Same refusal generate_voice makes before spend — staging IPA it would
    # never send would make tts_text.txt show text that is never spoken.
    err = (mcp_server._check_ipa_model(joined, model_id, label)
           or mcp_server._check_phoneme_model(joined, model_id, label))
    if err:
        raise SystemExit(err)
    tts_text = mcp_server._build_tts_text(joined, mode, lexicon)

    # Derived through the shared path layer, never joined by hand: the row
    # was found, but an id filed before ids were checked (`../outside`, an
    # absolute path) is still in the database, and a hand join writes there.
    try:
        job_dir = tjobs.job_dir(root / "jobs", video_id)
    except tjobs.UnsafePath as e:
        raise SystemExit(f"Video {video_id!r}: cannot stage, {e}")
    broll_path = job_dir / "script_with_broll.txt"
    tts_path = job_dir / "tts_text.txt"
    for path in (broll_path, tts_path):
        if path.is_symlink():  # write_text would follow it out of the job dir
            raise SystemExit(f"Video {video_id!r}: cannot stage, {path} is a symlink")
    job_dir.mkdir(parents=True, exist_ok=True)

    broll_path.write_text(_format_broll(segments))
    tts_path.write_text(tts_text.strip() + "\n")

    return broll_path, tts_path


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video_id")
    args = parser.parse_args(argv)

    root = _data_root()
    broll_path, tts_path = stage_script(args.video_id, root)
    print(f"Wrote {broll_path}")
    print(f"Wrote {tts_path}")


if __name__ == "__main__":
    main()
