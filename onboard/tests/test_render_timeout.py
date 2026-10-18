"""Render timeout onboarding (TMDEV-57): the minutes<->seconds conversion at
the load and write boundaries, and the 1-minute floor validator.

render_timeout_mins is onboard-only — it is never itself a settings-table
key. The real key, render_timeout_secs, is what renderer/api/pipeline.py and
worker.py actually read; the field exists so the wizard can ask in minutes
without either of those needing to change units.
"""
import sqlite3

import pytest

import onboard.actions as actions
from onboard.config import FIELDS_BY_KEY, fields_for_step, load_current_values
from onboard.executor import Executor, NullReporter


# ── The field itself ──────────────────────────────────────────────────────────

def test_field_asks_in_minutes_defaulting_to_40():
    field = FIELDS_BY_KEY["render_timeout_mins"]
    assert field.default == "40"
    assert field.source == "settings"


def test_validator_rejects_below_one_minute():
    field = FIELDS_BY_KEY["render_timeout_mins"]
    assert field.validator("0") is not None
    assert field.validator("-5") is not None
    assert field.validator("1") is None
    assert field.validator("40") is None


def test_field_is_asked_in_the_pipeline_settings_step():
    keys = [f.key for f in fields_for_step("pipeline_settings", full=True)]
    assert "render_timeout_mins" in keys
    # Advanced (TMDEV-74) — the minimal questionnaire seeds the default.
    assert "render_timeout_mins" not in [f.key for f in fields_for_step("pipeline_settings")]


# ── Load boundary: seconds (stored) -> minutes (displayed) ───────────────────

def _values_with_settings_row(tmp_path, key, value):
    db = tmp_path / "tubematic.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    if value is not None:
        con.execute("INSERT INTO settings VALUES (?, ?)", (key, value))
    con.commit()
    con.close()
    return load_current_values(repo_root=tmp_path, db_path=db)


def test_prefill_converts_stored_seconds_to_minutes(tmp_path):
    values = _values_with_settings_row(tmp_path, "render_timeout_secs", "2400")
    assert values["render_timeout_mins"] == "40"


def test_prefill_falls_back_to_default_when_unset(tmp_path):
    values = _values_with_settings_row(tmp_path, "render_timeout_secs", None)
    assert values["render_timeout_mins"] == "40"


def test_prefill_floors_at_one_minute_for_a_sub_60s_stored_value(tmp_path):
    """Shouldn't happen given the write-side floor, but a value edited outside
    onboard (dashboard, MCP) could in principle be low — don't display 0."""
    values = _values_with_settings_row(tmp_path, "render_timeout_secs", "45")
    assert values["render_timeout_mins"] == "1"


def test_prefill_ignores_corrupt_stored_value(tmp_path):
    values = _values_with_settings_row(tmp_path, "render_timeout_secs", "not-a-number")
    assert values["render_timeout_mins"] == "40"  # falls back to the field default


# ── Write boundary: minutes (answered) -> seconds (seeded) ───────────────────

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


def test_seeds_render_timeout_secs_from_minutes(tmp_path, monkeypatch):
    rows = _seed_and_read(tmp_path, {"render_timeout_mins": "45"})
    assert rows["render_timeout_secs"] == "2700"


def test_seeds_default_40_minutes_when_unanswered(tmp_path, monkeypatch):
    rows = _seed_and_read(tmp_path, {})
    assert rows["render_timeout_secs"] == "2400"


@pytest.mark.parametrize("raw", ["0", "-10"])
def test_seeding_clamps_out_of_range_to_the_one_minute_floor(tmp_path, monkeypatch, raw):
    """A parseable but out-of-range value clamps to the floor rather than
    resetting to the default — same philosophy as _clamp_nonneg_int for
    every other int setting in this function."""
    rows = _seed_and_read(tmp_path, {"render_timeout_mins": raw})
    assert rows["render_timeout_secs"] == "60"  # 1 minute, the floor


@pytest.mark.parametrize("raw", ["not-a-number", ""])
def test_seeding_falls_back_to_the_default_when_unparseable(tmp_path, monkeypatch, raw):
    """apply_pipeline_settings must never seed a value the settings API would
    itself reject (< 60s) — this is the same clamp-don't-crash philosophy
    every other int setting in this function already uses."""
    rows = _seed_and_read(tmp_path, {"render_timeout_mins": raw})
    assert rows["render_timeout_secs"] == "2400"
