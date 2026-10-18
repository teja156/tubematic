"""The install_config step: configuration is seeded into the settings table,
not written to .env (TMDEV-73).

Covers the step's two jobs — persist what it prompted, and gate on an
image-generation provider key — plus the ordering constraint that makes it
possible (the DB must exist first).
"""
import sqlite3

import pytest

import onboard.actions as actions
from onboard.config import ENV_FIELD_TO_SETTING
from onboard.executor import Executor, NullReporter


def _db(tmp_path):
    """A DB with just the settings table, as `database` would have left it."""
    db = tmp_path / "mounted" / "data" / "tubematic.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    return db


def _rows(db):
    con = sqlite3.connect(str(db))
    rows = dict(con.execute("SELECT key, value FROM settings").fetchall())
    con.close()
    return rows


def _apply(tmp_path, monkeypatch, values, *, dry_run=False):
    db = tmp_path / "mounted" / "data" / "tubematic.db"
    monkeypatch.setattr(actions, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(actions, "DB_PATH", db)
    cfg = type("Cfg", (), {"values": values})()
    actions.apply_install_config(cfg, Executor(dry_run=dry_run), NullReporter())
    return db


_MINIMAL = {"OPENAI_API_KEY": "oa-key"}


# ── Persistence ──────────────────────────────────────────────────────────────

def test_writes_every_prompted_field_to_its_settings_row(tmp_path, monkeypatch):
    _db(tmp_path)
    db = _apply(tmp_path, monkeypatch, {
        "ELEVENLABS_API_KEY": "el-key",
        "GEMINI_API_KEY": "g-key",
        "OPENAI_API_KEY": "oa-key",
        "YOUTUBE_TRANSCRIPT_API_KEY": "yt-key",
        "MCP_PORT": "4200",
    })
    rows = _rows(db)
    assert rows["elevenlabs_api_key"] == "el-key"
    assert rows["gemini_api_key"] == "g-key"
    assert rows["openai_api_key"] == "oa-key"
    assert rows["youtube_transcript_api_key"] == "yt-key"
    assert rows["mcp_port"] == "4200"


def test_writes_no_env_file(tmp_path, monkeypatch):
    """The whole point of the ticket — nothing should recreate .env."""
    _db(tmp_path)
    _apply(tmp_path, monkeypatch, _MINIMAL)
    assert not (tmp_path / ".env").exists()


def test_writes_no_agent_row(tmp_path, monkeypatch):
    """The agent's binary, workspace, scope and models belong to its agents row
    now, written by --install-agent (TMDEV-90) — not to settings, even when a
    stale answer for one is still in cfg.values."""
    _db(tmp_path)
    db = _apply(tmp_path, monkeypatch, {**_MINIMAL, "TUBEMATIC_AGENT": "claude",
                                        "AGENT_RUN_PATH": "/x", "INSTALL_SCOPE": "project"})
    assert not set(_rows(db)) & {"agent_model", "agent_binary", "agent_run_path",
                                 "install_scope"}


def test_dry_run_writes_nothing(tmp_path, monkeypatch):
    db = _db(tmp_path)
    _apply(tmp_path, monkeypatch, _MINIMAL, dry_run=True)
    assert _rows(db) == {}


def test_missing_database_warns_instead_of_crashing(tmp_path, monkeypatch):
    """The step is ordered after `database`, but --step can run it alone."""
    warned = []
    rep = NullReporter()
    rep.warn = lambda msg, *a, **k: warned.append(msg)
    monkeypatch.setattr(actions, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(actions, "DB_PATH", tmp_path / "mounted" / "data" / "tubematic.db")
    cfg = type("Cfg", (), {"values": _MINIMAL})()
    actions.apply_install_config(cfg, Executor(dry_run=False), rep)
    assert any("Database not initialised" in m for m in warned)


# ── The OpenAI-key gate (TMDEV-165) ──────────────────────────────────────────

@pytest.mark.parametrize("values", [
    {"GEMINI_API_KEY": "", "OPENAI_API_KEY": ""},
    {"GEMINI_API_KEY": "g", "OPENAI_API_KEY": ""},
])
def test_rejects_a_missing_openai_key(tmp_path, monkeypatch, values):
    """A Gemini key no longer draws images, so it no longer satisfies the gate."""
    _db(tmp_path)
    with pytest.raises(RuntimeError, match="No OpenAI API key configured"):
        _apply(tmp_path, monkeypatch, values)


def test_still_persists_everything_before_failing(tmp_path, monkeypatch):
    """The gate fires after the write on purpose — everything already typed has
    to survive so the re-prompted step can pre-fill it."""
    _db(tmp_path)
    db = tmp_path / "mounted" / "data" / "tubematic.db"
    with pytest.raises(RuntimeError):
        _apply(tmp_path, monkeypatch, {
            "GEMINI_API_KEY": "", "OPENAI_API_KEY": "", "ELEVENLABS_API_KEY": "el-key",
        })
    assert _rows(db)["elevenlabs_api_key"] == "el-key"


@pytest.mark.parametrize("values", [
    {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "o"},
    {"GEMINI_API_KEY": "g", "OPENAI_API_KEY": "o"},
])
def test_accepts_an_openai_key_with_or_without_gemini(tmp_path, monkeypatch, values):
    _db(tmp_path)
    _apply(tmp_path, monkeypatch, values)


# ── The mapping itself ───────────────────────────────────────────────────────

def test_every_mapped_row_is_lowercase(tmp_path):
    """Field keys stay uppercase (form identifiers); rows match every other
    settings key."""
    for row in ENV_FIELD_TO_SETTING.values():
        assert row == row.lower()


def test_mapping_has_no_duplicate_rows():
    rows = list(ENV_FIELD_TO_SETTING.values())
    assert len(rows) == len(set(rows))


def test_a_leftover_env_file_is_ignored_entirely(tmp_path, monkeypatch):
    """TMDEV-73 eliminates .env, including as a migration source: a stale file
    must not influence what gets stored, or deleting it would silently change
    the next onboarding run's answers."""
    _db(tmp_path)
    (tmp_path / ".env").write_text(
        "GEMINI_API_KEY=from-a-stale-file\nOPENAI_API_KEY=also-stale\n")
    db = _apply(tmp_path, monkeypatch, {"OPENAI_API_KEY": "typed-this-run"})
    rows = _rows(db)
    assert rows["openai_api_key"] == "typed-this-run"
    assert rows["gemini_api_key"] == ""


# ── TMDEV-83: publishing ─────────────────────────────────────────────────────

def test_the_publishing_answers_are_persisted(tmp_path, monkeypatch):
    _db(tmp_path)
    db = _apply(tmp_path, monkeypatch, {
        "OPENAI_API_KEY": "oa-key",
        "POSTFORME_API_KEY": "pfm-key",
        "PUBLISHING_ENABLED": "true",
    })
    rows = _rows(db)
    assert rows["postforme_api_key"] == "pfm-key"
    assert rows["publishing_enabled"] == "true"


def test_publishing_defaults_to_off_when_the_question_was_skipped(tmp_path, monkeypatch):
    """apply_install_config's `v.get(key, "<literal>")` fallbacks are a SECOND
    copy of every default (the TMDEV-74 trap). If this one drifts from the
    field spec, a skipped question silently enables publishing."""
    _db(tmp_path)
    rows = _rows(_apply(tmp_path, monkeypatch, dict(_MINIMAL)))
    assert rows["publishing_enabled"] == "false"
    assert rows["postforme_api_key"] == ""


def test_the_apply_side_default_matches_the_field_spec():
    """Pins the two copies together rather than trusting them to stay equal."""
    from onboard.config import FIELDS_BY_KEY
    assert FIELDS_BY_KEY["PUBLISHING_ENABLED"].default == "false"
