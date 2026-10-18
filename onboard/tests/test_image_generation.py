"""Image-generation onboarding (TMDEV-29; OpenAI-only since TMDEV-165): the
model select, and the OpenAI-key gate in apply_install_config."""
import pytest

import onboard.actions as actions
from onboard.config import (
    DEFAULT_IMAGE_MODEL,
    OPENAI_IMAGE_MODELS,
    FIELDS_BY_KEY,
    fields_for_step,
)
from onboard.executor import Executor, NullReporter


# ── The model select ──────────────────────────────────────────────────────────

def test_image_model_is_a_plain_select_over_the_openai_catalog():
    field = FIELDS_BY_KEY["image_model"]
    assert field.choices == OPENAI_IMAGE_MODELS
    assert field.dynamic_choices is None
    assert field.default == DEFAULT_IMAGE_MODEL == "gpt-image-2.5-flare"


def test_no_provider_question_is_asked():
    """The provider question went with the Gemini image models."""
    keys = [f.key for f in fields_for_step("pipeline_settings")]
    assert "image_provider" not in keys
    assert "image_model" in keys


# ── The key gate ──────────────────────────────────────────────────────────────

def _apply_env(tmp_path, monkeypatch, values):
    """apply_install_config against a throwaway settings table (TMDEV-73)."""
    import sqlite3
    db = tmp_path / "mounted" / "data" / "tubematic.db"
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    monkeypatch.setattr(actions, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(actions, "DB_PATH", db)
    cfg = type("Cfg", (), {"values": values})()
    actions.apply_install_config(cfg, Executor(dry_run=False), NullReporter())
    return db


@pytest.mark.parametrize("values", [
    {"GEMINI_API_KEY": "", "OPENAI_API_KEY": ""},
    # A Gemini key no longer draws images, so it no longer satisfies the gate.
    {"GEMINI_API_KEY": "g", "OPENAI_API_KEY": ""},
])
def test_apply_env_rejects_a_missing_openai_key(tmp_path, monkeypatch, values):
    with pytest.raises(RuntimeError, match="No OpenAI API key configured"):
        _apply_env(tmp_path, monkeypatch, values)


def test_apply_env_still_persists_before_failing(tmp_path, monkeypatch):
    """The gate fires after the settings write on purpose — everything already
    typed has to survive so the re-prompted step can pre-fill it."""
    import sqlite3
    with pytest.raises(RuntimeError):
        _apply_env(tmp_path, monkeypatch, {
            "GEMINI_API_KEY": "g", "OPENAI_API_KEY": "", "ELEVENLABS_API_KEY": "el-key",
        })
    con = sqlite3.connect(str(tmp_path / "mounted" / "data" / "tubematic.db"))
    rows = dict(con.execute("SELECT key, value FROM settings"))
    con.close()
    assert (rows["elevenlabs_api_key"], rows["gemini_api_key"]) == ("el-key", "g")


@pytest.mark.parametrize("values", [
    {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "o"},
    {"GEMINI_API_KEY": "g", "OPENAI_API_KEY": "o"},
])
def test_apply_env_accepts_an_openai_key_with_or_without_gemini(tmp_path, monkeypatch, values):
    _apply_env(tmp_path, monkeypatch, values)
    assert (tmp_path / "mounted" / "data" / "tubematic.db").exists()


def test_apply_env_writes_openai_key(tmp_path, monkeypatch):
    _apply_env(tmp_path, monkeypatch, {"GEMINI_API_KEY": "", "OPENAI_API_KEY": "sk-test"})
    import sqlite3
    con = sqlite3.connect(str(tmp_path / "mounted" / "data" / "tubematic.db"))
    row = con.execute("SELECT value FROM settings WHERE key='openai_api_key'").fetchone()
    con.close()
    assert row[0] == "sk-test"


# ── Seeding ───────────────────────────────────────────────────────────────────

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


@pytest.mark.parametrize("model", OPENAI_IMAGE_MODELS)
def test_seeds_the_model_and_no_provider(tmp_path, monkeypatch, model):
    rows = _seed_and_read(tmp_path, monkeypatch, {"image_model": model})
    assert rows["image_model"] == model
    assert "image_provider" not in rows


@pytest.mark.parametrize("stale", ["gemini-2.5-flash-image", "gpt-image-2", "nonsense"])
def test_a_stale_stored_model_is_corrected_on_a_rerun(tmp_path, monkeypatch, stale):
    """Onboarding reads settings before its database step migrates, so a re-run
    on an upgraded install can still see a retired model (TMDEV-148, TMDEV-165).
    The settings API allowlists image_model, so seeding it would 400 every save."""
    rows = _seed_and_read(tmp_path, monkeypatch, {"image_model": stale})
    assert rows["image_model"] == "gpt-image-2.5-flare"


def test_seeds_defaults_when_unanswered(tmp_path, monkeypatch):
    rows = _seed_and_read(tmp_path, monkeypatch, {})
    assert rows["image_model"] == "gpt-image-2.5-flare"
    assert "image_provider" not in rows
