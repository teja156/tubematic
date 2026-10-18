"""The agent-model shape validator (TMDEV-63), and the flat agent settings'
retirement from the main flow (TMDEV-90).

Models are now a per-agent list, entered and probed by `--install-agent`
(onboard/agent_install.py — see test_agent_install.py). What survives here is
the shape check every entry still passes first, and the pin that the main
flow neither asks about an agent nor writes any agent row into settings.
"""
import sqlite3

import onboard.actions as actions
from onboard.config import ENV_FIELD_TO_SETTING, FIELDS_BY_KEY, _agent_model


def test_validator_accepts_an_alias_and_a_full_id():
    assert _agent_model("sonnet") is None
    assert _agent_model("claude-sonnet-4-5-20250929") is None


def test_validator_rejects_spaces_and_flag_like_values():
    assert _agent_model("sonnet opus") is not None
    assert _agent_model("-p") is not None
    assert _agent_model(" sonnet") is not None


def test_no_main_flow_question_is_about_the_agent():
    for key in ("TUBEMATIC_AGENT", "TUBEMATIC_AGENT_MODEL", "AGENT_RUN_PATH",
                "INSTALL_SCOPE", "WIPE_AGENT_WORKSPACE"):
        assert key not in FIELDS_BY_KEY, key
    retired = {"agent_model", "agent_binary", "agent_run_path", "install_scope"}
    assert not retired & set(ENV_FIELD_TO_SETTING.values())


def test_install_config_writes_no_agent_row(tmp_path, monkeypatch):
    db = tmp_path / "tubematic.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    monkeypatch.setattr(actions, "DB_PATH", db)
    cfg = type("Cfg", (), {"values": {"OPENAI_API_KEY": "x"}})()
    actions.apply_install_config(cfg, actions.Executor(dry_run=False), actions.NullReporter())
    con = sqlite3.connect(str(db))
    keys = {k for (k,) in con.execute("SELECT key FROM settings")}
    con.close()
    assert not keys & {"agent_model", "agent_binary", "agent_run_path", "install_scope"}
