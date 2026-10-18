"""0006 — every voice carries its own ElevenLabs model (TMDEV-121).

Before this, one install-wide settings row (elevenlabs_model_id) chose the
model for every voice. Now each elevenlabs_voices entry has a model_id and the
install-wide row is gone. This migration stamps each existing voice with the
model the install was using, so every video's effective model is unchanged by
the upgrade, and then deletes the row. It also adds projects.default_voice_id,
the voice new videos in a domain are seeded with.

Python rather than SQL: the roster is a JSON document inside one settings row,
and rewriting entries conditionally is not something a .sql file can say
cleanly.

The model list is hardcoded here on purpose rather than imported from
tubematic_core.voice_models. A shipped migration must do the same thing
forever; importing a module that later gains or loses a model would silently
change what this file does on a database that has not run it yet.

A roster that is not a JSON list is left alone — every reader already treats a
corrupt roster as empty, and there is nothing trustworthy to stamp. A missing
roster row (a fresh database) is left alone too: onboarding seeds the new shape
after the schema exists.

One-way. 1.1.0's readers accept only {name, voice_id} entries and would read a
stamped roster as empty, so a rollback means restoring the automatic
pre-migration backup.

*** THIS FILE HAS SHIPPED ONCE MERGED. DO NOT EDIT IT. ***
"""
import json

_MODELS = (
    "eleven_multilingual_v2",
    "eleven_v3",
    "eleven_flash_v2_5",
    "eleven_turbo_v2_5",
    "eleven_flash_v2",
    "eleven_turbo_v2",
)
_FALLBACK = "eleven_multilingual_v2"


def up(con):
    row = con.execute(
        "SELECT value FROM settings WHERE key = 'elevenlabs_model_id'").fetchone()
    stored = (row[0] or "").strip() if row else ""
    # A retired model (eleven_english_v1 was removed from the catalog in
    # 1.1.1) or a blank row falls back rather than being carried onto voices
    # where nothing could voice with it.
    install_model = stored if stored in _MODELS else _FALLBACK

    row = con.execute(
        "SELECT value FROM settings WHERE key = 'elevenlabs_voices'").fetchone()
    if row is not None:
        try:
            roster = json.loads(row[0])
        except (TypeError, ValueError):
            roster = None
        if isinstance(roster, list):
            changed = False
            for entry in roster:
                if isinstance(entry, dict) and entry.get("model_id") not in _MODELS:
                    entry["model_id"] = install_model
                    changed = True
            if changed:
                con.execute(
                    "UPDATE settings SET value = ? WHERE key = 'elevenlabs_voices'",
                    (json.dumps(roster),))

    con.execute("DELETE FROM settings WHERE key = 'elevenlabs_model_id'")
    con.execute(
        "ALTER TABLE projects ADD COLUMN default_voice_id TEXT NOT NULL DEFAULT ''")
