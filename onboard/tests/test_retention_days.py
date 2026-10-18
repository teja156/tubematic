"""Video retention onboarding (TMDEV-84): the retention_days field and the
settings row apply_pipeline_settings seeds from it.

The field is advanced, so on a minimal install it is never asked and the seed
comes entirely from the `v.get(key, "<literal>")` fallback in
apply_pipeline_settings — a second copy of the default that has to match
SETTINGS_SPEC's, or a skipped question silently seeds a different number.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

import onboard.actions as actions
from onboard.config import (
    FIELDS_BY_KEY, MAX_RETENTION_DAYS, MIN_RETENTION_DAYS, fields_for_step,
)
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


def test_the_field_is_advanced_and_settings_sourced():
    assert FIELDS_BY_KEY["retention_days"].source == "settings"
    assert "retention_days" in [f.key for f in fields_for_step("pipeline_settings", full=True)]
    assert "retention_days" not in [f.key for f in fields_for_step("pipeline_settings")]


def test_all_three_default_copies_agree():
    spec_default = pipeline.SETTINGS_SPEC["retention_days"][1]
    assert FIELDS_BY_KEY["retention_days"].default == spec_default == "7"


def test_a_skipped_question_seeds_the_spec_default(tmp_path):
    rows = _seed_and_read(tmp_path, {})
    assert rows["retention_days"] == pipeline.SETTINGS_SPEC["retention_days"][1]


def test_an_answered_value_is_seeded(tmp_path):
    assert _seed_and_read(tmp_path, {"retention_days": "30"})["retention_days"] == "30"


def test_zero_is_seeded_as_zero_not_clamped(tmp_path):
    """0 is the off switch. A floor of 1 here would silently turn it back on."""
    assert _seed_and_read(tmp_path, {"retention_days": "0"})["retention_days"] == "0"


def test_the_bounds_match_the_settings_api():
    assert (MIN_RETENTION_DAYS, MAX_RETENTION_DAYS) == (
        pipeline.MIN_RETENTION_DAYS, pipeline.MAX_RETENTION_DAYS)


@pytest.mark.parametrize("value,ok", [
    ("0", True), ("7", True), ("365", True), ("-1", False), ("366", False), ("abc", False),
])
def test_the_validator_mirrors_the_settings_api(value, ok):
    assert (FIELDS_BY_KEY["retention_days"].validator(value) is None) is ok
