"""Auto Pilot onboarding (TMDEV-139): the auto_pilot_enabled field and the
settings row apply_pipeline_settings seeds from it.

Auto Pilot removes every human checkpoint, so the two things pinned here are
that the minimal questionnaire never asks about it, and that nothing short of
an explicit "true" can seed it on.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

import onboard.actions as actions
from onboard.config import FIELDS_BY_KEY, fields_for_step
from onboard.executor import Executor, NullReporter

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "renderer" / "api"))
import pipeline  # noqa: E402


def _seed_and_read(tmp_path, values):
    db = tmp_path / "tubematic.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    actions.DB_PATH = db
    cfg = type("Cfg", (), {"values": values})()
    actions.apply_pipeline_settings(cfg, Executor(dry_run=False), NullReporter())
    con = sqlite3.connect(str(db))
    rows = dict(con.execute("SELECT key, value FROM settings"))
    con.close()
    return rows


def test_the_minimal_questionnaire_never_asks_about_auto_pilot():
    assert FIELDS_BY_KEY["auto_pilot_enabled"].source == "settings"
    assert "auto_pilot_enabled" in [
        f.key for f in fields_for_step("pipeline_settings", full=True)]
    assert "auto_pilot_enabled" not in [f.key for f in fields_for_step("pipeline_settings")]


def test_it_is_off_by_default_in_every_copy():
    assert FIELDS_BY_KEY["auto_pilot_enabled"].default == "false"
    assert pipeline.SETTINGS_SPEC["auto_pilot_enabled"][1] == "false"


def test_a_skipped_question_seeds_it_off(tmp_path):
    assert _seed_and_read(tmp_path, {})["auto_pilot_enabled"] == "false"


@pytest.mark.parametrize("answer,seeded", [
    ("true", "true"), ("false", "false"), ("", "false"), ("yes", "false"), ("1", "false"),
])
def test_only_an_explicit_true_turns_it_on(tmp_path, answer, seeded):
    rows = _seed_and_read(tmp_path, {"auto_pilot_enabled": answer})
    assert rows["auto_pilot_enabled"] == seeded


def test_the_question_carries_the_warning():
    text = FIELDS_BY_KEY["auto_pilot_enabled"].help
    for phrase in ("no human review", "posts publicly", "cannot be taken back"):
        assert phrase in text
