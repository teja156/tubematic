#!/usr/bin/env python3
"""Generate the VQA seed database.

Run at image-build time (see dockerfile_tubematic_vqa) so a fresh VQA session
never has to run onboard.py's `database`/`pipeline_settings` steps. Uses the
canonical schema from tubematic_core/migrations/, which is the one definition
every process shares (TMDEV-91).

Seeds exactly what's needed before a human can create a video and voice it:
  - one project (`proj_vqa`) — create_video errors on an unknown project_id
  - elevenlabs_voices / elevenlabs_voice_id — generate_voice hard-errors with
    "No default voice set" without these, before any spend
  - gemini_review_enabled=false — VQA review is on-demand (vqa/review_video.py),
    not the worker's automatic post-render pass; see vqa/README.md
Every other settings key is left unset and resolves to its SETTINGS_SPEC
default at read time.

Usage: make_seed_db.py [output_path]  (default: vqa/seed/tubematic.db)
"""
import sqlite3
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "renderer" / "api"))

from pipeline import SETTINGS_SPEC, _coerce_setting  # noqa: E402
from tubematic_core import db as tdb  # noqa: E402

DEFAULT_OUTPUT = REPO_ROOT / "vqa" / "seed" / "tubematic.db"

VQA_PROJECT_ID = "proj_vqa"

# ElevenLabs' standard premade "Rachel" voice — a real, publicly documented
# preset ID (used throughout ElevenLabs' own API examples), not a placeholder
# that needs editing before generate_voice will work. Replace via the roster
# (settings.elevenlabs_voices) if a different voice is preferred.
_DEFAULT_VOICE_ID = "21m00Tcm4TlvDq8ikWAM"
_DEFAULT_VOICE_NAME = "Rachel"

# Settings seeded beyond SETTINGS_SPEC's own defaults. Every other key
# (research caps, trending_sources, active_strategies, ...) is intentionally
# left unset — VQA has no cron/research, and an absent key resolves to the
# SETTINGS_SPEC default at read time, so there's nothing to seed for it.
_SETTINGS = {
    "gemini_review_enabled": "false",
    # Each voice carries its own model (TMDEV-121). Written after
    # tdb.migrate, so migration 0006 never sees it — it must already be in
    # the current shape.
    "elevenlabs_voices": [{"name": _DEFAULT_VOICE_NAME, "voice_id": _DEFAULT_VOICE_ID,
                           "model_id": "eleven_multilingual_v2"}],
    "elevenlabs_voice_id": _DEFAULT_VOICE_ID,
    "image_model": "gpt-image-2.5-flare",
    "render_timeout_secs": "2700",
    "max_render_retries": "1",
    "pipeline_paused": "false",
}


def make_seed_db(output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if output_path.exists():
        output_path.unlink()
    for suffix in ("-wal", "-shm"):
        sidecar = output_path.with_name(output_path.name + suffix)
        if sidecar.exists():
            sidecar.unlink()

    tdb.migrate(output_path)  # canonical schema, from tubematic_core/migrations/

    con = sqlite3.connect(str(output_path))
    try:
        con.execute(
            "INSERT INTO projects (id, name, description, is_curriculum_seed, status, created_at) "
            "VALUES (?, ?, ?, 0, 'active', datetime('now')) "
            "ON CONFLICT(id) DO NOTHING",
            (VQA_PROJECT_ID, "VQA Test Bench", "Manually-driven videos created in the VQA environment."),
        )

        for key, raw in _SETTINGS.items():
            assert key in SETTINGS_SPEC, f"{key!r} is not a recognized setting"
            _, db_str = _coerce_setting(key, raw)  # validates + normalizes, matches POST /settings
            con.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, db_str),
            )

        con.commit()
        # migrate() runs in WAL mode. Checkpoint before closing so every commit
        # lands in the .db file itself — kasm_post_run_user.sh copies just that one
        # file (no -wal/-shm sidecar), and a lingering WAL file would silently
        # drop these inserts from the copy.
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        con.close()


if __name__ == "__main__":
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_OUTPUT
    make_seed_db(out)
    print(f"Seed DB written to {out}")
