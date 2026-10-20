"""Config loading defaults: pre-fill from an existing .env + seeded settings
table, falling back to the field's declared default otherwise."""
import json
import sqlite3

from onboard.config import (
    load_current_values, read_settings, writable_parent,
    _positive_int, _nonneg_int,
)


def test_read_settings_missing_db_returns_empty(tmp_path):
    assert read_settings(tmp_path / "nonexistent.db") == {}


def test_read_settings_reads_rows(tmp_path):
    db_path = tmp_path / "db.sqlite"
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO settings VALUES ('trending_sources', ?)", (json.dumps(["Lobsters"]),))
    con.commit()
    con.close()
    settings = read_settings(db_path)
    assert json.loads(settings["trending_sources"]) == ["Lobsters"]


def test_load_current_values_env_field_reads_its_mapped_settings_row(tmp_path):
    """Field keys stay uppercase (they are form identifiers); the value lives
    in the settings table under the mapped lowercase row (TMDEV-73)."""
    db_path = tmp_path / "db.sqlite"
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO settings VALUES ('mcp_port', '9999')")
    con.commit()
    con.close()
    values = load_current_values(repo_root=tmp_path, db_path=db_path)
    assert values["MCP_PORT"] == "9999"


def test_load_current_values_ignores_a_leftover_env_file(tmp_path):
    """.env is not a source of truth, a fallback, or a migration path — a stale
    file must not change what the wizard offers."""
    (tmp_path / ".env").write_text("MCP_PORT=9999\nGEMINI_API_KEY=stale\n")
    values = load_current_values(repo_root=tmp_path, db_path=tmp_path / "missing.db")
    assert values["MCP_PORT"] == "4100"       # field default, not the file
    assert values["GEMINI_API_KEY"] == ""


def test_load_current_values_falls_back_to_default(tmp_path):
    values = load_current_values(repo_root=tmp_path, db_path=tmp_path / "missing.db")
    assert values["MCP_PORT"] == "4100"  # Field default
    assert values["POLL_INTERVAL_MINS"] == "30"


def test_load_current_values_settings_field_from_db(tmp_path):
    db_path = tmp_path / "db.sqlite"
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO settings VALUES ('max_curriculum_per_run', '7')")
    con.commit()
    con.close()
    values = load_current_values(repo_root=tmp_path, db_path=db_path)
    assert values["max_curriculum_per_run"] == "7"


def test_ephemeral_field_never_reads_from_disk(tmp_path, monkeypatch):
    # No main-flow field is ephemeral since the wipe question moved to
    # --install-agent (TMDEV-90), so the branch is pinned with a stand-in.
    from onboard import config
    monkeypatch.setitem(config.FIELDS_BY_KEY, "ONE_SHOT_CONFIRM", config.Field(
        "ONE_SHOT_CONFIRM", "Confirm?", help="h", source="ephemeral", default="false"))
    db_path = tmp_path / "db.sqlite"
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO settings VALUES ('ONE_SHOT_CONFIRM', 'true')")
    con.commit()
    con.close()
    values = load_current_values(repo_root=tmp_path, db_path=db_path)
    assert values["ONE_SHOT_CONFIRM"] == "false"  # field default, stored value ignored


def test_read_agents_parses_models_and_survives_a_missing_table(tmp_path):
    from onboard.config import read_agents
    db_path = tmp_path / "db.sqlite"
    assert read_agents(db_path) == []                       # no database
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    con.commit()
    assert read_agents(db_path) == []                       # no agents table yet
    con.execute("CREATE TABLE agents (id TEXT PRIMARY KEY, models TEXT, created_at TEXT)")
    con.execute("INSERT INTO agents VALUES ('claude', '[\"opus\", 3]', '1')")
    con.execute("INSERT INTO agents VALUES ('broken', 'not json', '2')")
    con.commit()
    con.close()
    rows = read_agents(db_path)
    assert [r["id"] for r in rows] == ["claude", "broken"]
    assert rows[0]["models"] == ["opus"]
    assert rows[1]["models"] == []


def test_writable_parent_validator(tmp_path):
    assert writable_parent("") is None
    assert writable_parent(str(tmp_path / "does" / "not" / "exist" / "yet")) is None
    # A path under a directory we can't even stat (permission denied) must
    # return a validation message, not raise.
    assert writable_parent("/root/definitely-not-writable-xyz") is not None


def test_int_validators():
    assert _positive_int("5") is None
    assert _positive_int("0") is not None
    assert _positive_int("abc") is not None
    assert _nonneg_int("0") is None
    assert _nonneg_int("-1") is not None


def test_a_fresh_install_offers_the_pre_loaded_voices(tmp_path):
    """No database yet: the voice questions fall back to their defaults, which
    is how a fresh install gets the pre-loaded roster (TMDEV-172)."""
    from tubematic_core import voice_models
    values = load_current_values(repo_root=tmp_path, db_path=tmp_path / "missing.db")
    assert json.loads(values["elevenlabs_voices"]) == list(voice_models.DEFAULT_VOICES)
    assert values["elevenlabs_voice_id"] == voice_models.DEFAULT_VOICE_ID


def test_a_stored_empty_roster_is_not_refilled_with_the_pre_loaded_voices(tmp_path):
    """Someone who deleted every voice (the pre-loaded ones included) must not
    get them back by re-running onboarding."""
    db_path = tmp_path / "db.sqlite"
    con = sqlite3.connect(str(db_path))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    con.execute("INSERT INTO settings VALUES ('elevenlabs_voices', '[]')")
    con.execute("INSERT INTO settings VALUES ('elevenlabs_voice_id', '')")
    con.commit()
    con.close()
    values = load_current_values(repo_root=tmp_path, db_path=db_path)
    assert values["elevenlabs_voices"] == "[]"
    assert values["elevenlabs_voice_id"] == ""
