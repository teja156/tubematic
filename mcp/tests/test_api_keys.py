"""API keys are read from the settings table, per call (TMDEV-73).

Before this, the three keys were module-level constants captured from the
environment at import time, so rotating one meant restarting the container.
They now come from the DB — with env kept purely as a fallback, so a compose
`environment:` entry (which is how docker-compose.test.yml supplies dummy
keys) still works.

Requires the mcp/ package deps — see mcp/requirements.txt.
Run from repo root: pytest mcp/tests/
"""

import pytest

import server

HELPERS = [
    ("elevenlabs_api_key", "ELEVENLABS_API_KEY", "_elevenlabs_key"),
    ("gemini_api_key",     "GEMINI_API_KEY",     "_gemini_key"),
    ("openai_api_key",     "OPENAI_API_KEY",     "_openai_key"),
]


@pytest.fixture
def db(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "DB_FILE", tmp_path / "test.db")
    server._init_db()


@pytest.mark.parametrize("setting_key,env_var,helper", HELPERS)
def test_key_comes_from_the_settings_table(db, monkeypatch, setting_key, env_var, helper):
    monkeypatch.delenv(env_var, raising=False)
    server._set_setting(setting_key, "from-db")
    assert getattr(server, helper)() == "from-db"


@pytest.mark.parametrize("setting_key,env_var,helper", HELPERS)
def test_settings_row_wins_over_the_environment(db, monkeypatch, setting_key, env_var, helper):
    monkeypatch.setenv(env_var, "from-env")
    server._set_setting(setting_key, "from-db")
    assert getattr(server, helper)() == "from-db"


@pytest.mark.parametrize("setting_key,env_var,helper", HELPERS)
def test_environment_is_the_fallback_when_no_row_exists(db, monkeypatch, setting_key, env_var, helper):
    """Keeps docker-compose.test.yml's `environment:` injection working without
    seeding the e2e database."""
    monkeypatch.setenv(env_var, "from-env")
    assert getattr(server, helper)() == "from-env"


@pytest.mark.parametrize("setting_key,env_var,helper", HELPERS)
def test_blank_row_falls_through_to_the_environment(db, monkeypatch, setting_key, env_var, helper):
    """A cleared key is not a configured empty key — onboarding seeds "" for
    every credential it did not ask for, and that must not shadow a real env
    value."""
    monkeypatch.setenv(env_var, "from-env")
    server._set_setting(setting_key, "")
    assert getattr(server, helper)() == "from-env"


@pytest.mark.parametrize("setting_key,env_var,helper", HELPERS)
def test_missing_everywhere_is_empty(db, monkeypatch, setting_key, env_var, helper):
    monkeypatch.delenv(env_var, raising=False)
    assert getattr(server, helper)() == ""


@pytest.mark.parametrize("setting_key,env_var,helper", HELPERS)
def test_rotation_takes_effect_without_reimport(db, monkeypatch, setting_key, env_var, helper):
    """The whole point of reading per call: a key changed on the Settings
    dashboard applies to the next tool call, with no container restart."""
    monkeypatch.delenv(env_var, raising=False)
    server._set_setting(setting_key, "old-key")
    assert getattr(server, helper)() == "old-key"
    server._set_setting(setting_key, "rotated-key")
    assert getattr(server, helper)() == "rotated-key"


def test_no_key_is_captured_at_import_time():
    """A module-level constant would silently reintroduce the restart
    requirement, and no other test would notice."""
    for _, env_var, _ in HELPERS:
        assert not hasattr(server, env_var)
