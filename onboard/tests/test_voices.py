"""ElevenLabs voice roster onboarding (TMDEV-51): the voices/default-voice
dependent pair, _parse_voices' corrupt-value handling, and default-voice
fallback-to-first-entry behavior."""
import json

import onboard.actions as actions
from onboard.config import (
    FIELDS_BY_KEY, MAX_VOICES, _parse_voices, _stamp_legacy_voices, fields_for_step,
    load_current_values,
)
from onboard.executor import Executor, NullReporter


# ── _parse_voices ─────────────────────────────────────────────────────────────

def test_parse_voices_valid_list():
    raw = json.dumps([{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}])
    assert _parse_voices(raw) == [{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}]


def test_parse_voices_blank_or_none_returns_empty():
    assert _parse_voices("") == []
    assert _parse_voices(None) == []


def test_parse_voices_corrupt_json_returns_empty():
    assert _parse_voices("not json") == []


def test_parse_voices_over_cap_returns_empty():
    voices = [{"name": f"v{i}", "voice_id": f"id{i}", "model_id": "eleven_multilingual_v2"} for i in range(MAX_VOICES + 1)]
    assert _parse_voices(json.dumps(voices)) == []


def test_parse_voices_bad_shape_returns_empty():
    assert _parse_voices(json.dumps([{"name": "x"}])) == []
    assert _parse_voices(json.dumps([{"name": "", "voice_id": "x", "model_id": "eleven_multilingual_v2"}])) == []
    assert _parse_voices(json.dumps("not-a-list")) == []


def test_parse_voices_needs_a_known_model_on_every_voice():
    """Each voice carries its own model (TMDEV-121). A voice without one, or on
    a retired model, could never be voiced."""
    assert _parse_voices(json.dumps([{"name": "A", "voice_id": "a"}])) == []
    assert _parse_voices(json.dumps(
        [{"name": "A", "voice_id": "a", "model_id": "eleven_english_v1"}])) == []


# ── A re-run against an install from before per-voice models ─────────────────

def test_a_legacy_roster_is_stamped_with_the_install_model():
    legacy = json.dumps([{"name": "A", "voice_id": "a"}, {"name": "B", "voice_id": "b"}])
    out = json.loads(_stamp_legacy_voices(legacy, "eleven_v3"))
    assert [v["model_id"] for v in out] == ["eleven_v3", "eleven_v3"]


def test_a_legacy_roster_on_a_retired_model_falls_back_to_the_default():
    legacy = json.dumps([{"name": "A", "voice_id": "a"}])
    assert json.loads(_stamp_legacy_voices(legacy, "eleven_english_v1"))[0]["model_id"] \
        == "eleven_multilingual_v2"
    assert json.loads(_stamp_legacy_voices(legacy, None))[0]["model_id"] \
        == "eleven_multilingual_v2"


def test_a_current_roster_is_returned_untouched():
    current = json.dumps([{"name": "A", "voice_id": "a", "model_id": "eleven_flash_v2"}])
    assert _stamp_legacy_voices(current, "eleven_v3") == current
    assert _stamp_legacy_voices("not json", "eleven_v3") == "not json"


def test_load_current_values_reads_a_pre_migration_roster_as_a_real_one(tmp_path):
    """Onboarding reads stored values BEFORE its database step migrates. A
    strict read of an old {name, voice_id} roster would be empty, and applying
    that answer set would wipe the real roster."""
    import sqlite3
    db = tmp_path / "tubematic.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.executemany("INSERT INTO settings VALUES (?, ?)", [
        ("elevenlabs_voices", json.dumps([{"name": "A", "voice_id": "a"}])),
        ("elevenlabs_model_id", "eleven_turbo_v2")])
    con.commit()
    con.close()
    values = load_current_values(db_path=db)
    assert _parse_voices(values["elevenlabs_voices"]) == [
        {"name": "A", "voice_id": "a", "model_id": "eleven_turbo_v2"}]


# ── The dependent pair ────────────────────────────────────────────────────────

def test_default_voice_choices_follow_the_roster():
    field = FIELDS_BY_KEY["elevenlabs_voice_id"]
    roster = json.dumps([{"name": "A", "voice_id": "va", "model_id": "eleven_multilingual_v2"}, {"name": "B", "voice_id": "vb", "model_id": "eleven_multilingual_v2"}])
    assert field.dynamic_choices({"elevenlabs_voices": roster}) == ["va", "vb"]


def test_default_voice_choices_empty_when_roster_unanswered():
    field = FIELDS_BY_KEY["elevenlabs_voice_id"]
    assert field.dynamic_choices({}) == []


def test_voices_asked_before_default():
    keys = [f.key for f in fields_for_step("pipeline_settings", full=True)]
    assert keys.index("elevenlabs_voices") < keys.index("elevenlabs_voice_id")


# ── Seeding (apply_pipeline_settings) ────────────────────────────────────────

def _seed_and_read(tmp_path, monkeypatch, values):
    import sqlite3
    db = tmp_path / "tubematic.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    monkeypatch.setattr(actions, "DB_PATH", db)
    cfg = type("Cfg", (), {"values": values})()
    actions.apply_pipeline_settings(cfg, Executor(dry_run=False), NullReporter())
    con = sqlite3.connect(str(db))
    rows = dict(con.execute("SELECT key, value FROM settings"))
    con.close()
    return rows


def test_seeds_roster_and_default(tmp_path, monkeypatch):
    voices = [{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}]
    rows = _seed_and_read(tmp_path, monkeypatch, {
        "elevenlabs_voices": json.dumps(voices),
        "elevenlabs_voice_id": "abc123",
    })
    assert json.loads(rows["elevenlabs_voices"]) == voices
    assert rows["elevenlabs_voice_id"] == "abc123"
    # There is no install-wide model any more; each voice carries its own.
    assert "elevenlabs_model_id" not in rows


def test_default_not_in_roster_falls_back_to_first_entry(tmp_path, monkeypatch):
    voices = [{"name": "Narrator", "voice_id": "abc123", "model_id": "eleven_multilingual_v2"}]
    rows = _seed_and_read(tmp_path, monkeypatch, {
        "elevenlabs_voices": json.dumps(voices),
        "elevenlabs_voice_id": "stale_default",
    })
    assert rows["elevenlabs_voice_id"] == "abc123"


def test_empty_roster_and_no_default_seeds_empty(tmp_path, monkeypatch):
    rows = _seed_and_read(tmp_path, monkeypatch, {})
    assert json.loads(rows["elevenlabs_voices"]) == []
    assert rows["elevenlabs_voice_id"] == ""
