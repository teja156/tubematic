"""AI-review onboarding (VQA-7): the model/fps/loop-cap fields, their
validators, and the settings rows apply_pipeline_settings seeds from them.

The recurring theme in the seeding tests is that apply_pipeline_settings must
never write a value the settings API would itself reject — a mismatch there
leaves the dashboard 400ing on the next save of an unrelated key.
"""
import sqlite3

import pytest

import onboard.actions as actions
from onboard.config import (
    AI_REVIEW_MODELS,
    DEFAULT_AI_REVIEW_MODEL,
    MAX_AI_REVIEW_FPS,
    MAX_AI_REVIEW_LOOPS,
    FIELDS_BY_KEY,
    fields_for_step,
)
from onboard.executor import Executor, NullReporter


# ── Field specs ───────────────────────────────────────────────────────────

def test_all_three_fields_are_asked_in_the_pipeline_settings_step():
    keys = [f.key for f in fields_for_step("pipeline_settings", full=True)]
    minimal = [f.key for f in fields_for_step("pipeline_settings")]
    for key in ("ai_review_model", "ai_review_fps", "ai_review_max_loops"):
        assert key in keys
        # Advanced (TMDEV-74) — seeded from the defaults asserted below,
        # and editable afterwards on the Settings dashboard.
        assert key not in minimal


def test_fields_write_to_the_settings_table_not_env():
    """Unlike MAX_RENDER_RETRIES (a .env key seeded into settings), these are
    settings-table-native — there is no .env representation to drift from."""
    for key in ("ai_review_model", "ai_review_fps", "ai_review_max_loops"):
        assert FIELDS_BY_KEY[key].source == "settings"


def test_model_choices_are_the_review_catalog_and_default_to_the_cheapest():
    field = FIELDS_BY_KEY["ai_review_model"]
    assert field.choices == AI_REVIEW_MODELS
    # Existing installs must not silently get a pricier model on upgrade.
    assert field.default == "gemini-2.5-flash" == DEFAULT_AI_REVIEW_MODEL


def test_model_help_states_the_real_cost_multiple_not_the_headline_one():
    """The 3.x models list at 5x gemini-2.5-flash's token price but tokenise
    video ~3.7x more cheaply, so per video reviewed they are only ~1.4x. The
    headline number would talk someone out of a nearly-free upgrade."""
    help_text = FIELDS_BY_KEY["ai_review_model"].help
    assert "1.4x" in help_text
    assert "gemini-3.6-flash" in help_text


def test_review_loop_and_render_retry_caps_are_separate_fields():
    """The split (VQA-7): one knob used to cap both, so lowering the review
    loop silently halved the render retry budget.

    Deliberately structural rather than value-based. Both defaults are 1 as of
    TMDEV-74, so asserting they *differ* would have pinned a coincidence and
    would have broken the moment either default moved — the property that
    matters is that they are two fields writing two different settings rows.
    """
    from onboard.config import ENV_FIELD_TO_SETTING
    assert FIELDS_BY_KEY["ai_review_max_loops"].source == "settings"
    assert ENV_FIELD_TO_SETTING["MAX_RENDER_RETRIES"] == "max_render_retries"
    assert "ai_review_max_loops" not in ENV_FIELD_TO_SETTING.values()
    # ...and the relabelled render field no longer claims to be the AI loop.
    assert "render" in FIELDS_BY_KEY["MAX_RENDER_RETRIES"].label.lower()
    assert "review" not in FIELDS_BY_KEY["MAX_RENDER_RETRIES"].label.lower()


# ── Validators ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("good", ["1", "10", str(MAX_AI_REVIEW_FPS)])
def test_fps_validator_accepts_the_documented_range(good):
    assert FIELDS_BY_KEY["ai_review_fps"].validator(good) is None


@pytest.mark.parametrize("bad", ["0", "-1", "25", "100", "abc", ""])
def test_fps_validator_rejects_outside_it(bad):
    """Gemini's valid videoMetadata.fps range is (0, 24]; outside it the
    request 400s and the review fails open, shipping the video unreviewed."""
    assert FIELDS_BY_KEY["ai_review_fps"].validator(bad) is not None


@pytest.mark.parametrize("good", ["1", "2"])
def test_loop_validator_accepts_one_and_two(good):
    assert FIELDS_BY_KEY["ai_review_max_loops"].validator(good) is None


@pytest.mark.parametrize("bad", ["0", "3", "-1", "abc", ""])
def test_loop_validator_rejects_outside_one_to_two(bad):
    """0 is rejected rather than meaning 'review once': the routing boundary
    is `count > cap`, so 0 forces acceptance before any revision round."""
    assert FIELDS_BY_KEY["ai_review_max_loops"].validator(bad) is not None
    assert MAX_AI_REVIEW_LOOPS == 2


# ── Write boundary ────────────────────────────────────────────────────────

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


def test_seeds_the_answered_values(tmp_path):
    rows = _seed_and_read(tmp_path, {
        "ai_review_model": "gemini-3.6-flash",
        "ai_review_fps": "24",
        "ai_review_max_loops": "2",
    })
    assert rows["ai_review_model"] == "gemini-3.6-flash"
    assert rows["ai_review_fps"] == "24"
    assert rows["ai_review_max_loops"] == "2"


def test_seeds_defaults_when_unanswered(tmp_path):
    rows = _seed_and_read(tmp_path, {})
    assert rows["ai_review_model"] == "gemini-2.5-flash"
    assert rows["ai_review_fps"] == "10"
    assert rows["ai_review_max_loops"] == "1"
    # The render retry budget is seeded independently, from its own field.
    assert rows["max_render_retries"] == "1"


# ── Review off by default (TMDEV-165) ─────────────────────────────────────────
# Four copies of one default. The apply-side fallbacks are the easy miss: they
# are what a skipped or garbled answer lands on, so drifting back to "true"
# would switch review on for exactly the installs that never answered.

def test_review_is_off_when_the_question_was_skipped(tmp_path):
    assert _seed_and_read(tmp_path, {})["gemini_review_enabled"] == "false"


@pytest.mark.parametrize("raw", ["yes", "", "TRUE-ish"])
def test_a_garbled_review_answer_lands_on_off(tmp_path, raw):
    assert _seed_and_read(tmp_path, {"GEMINI_REVIEW_ENABLED": raw})["gemini_review_enabled"] == "false"


def test_an_explicit_yes_still_turns_review_on(tmp_path):
    assert _seed_and_read(tmp_path, {"GEMINI_REVIEW_ENABLED": "true"})["gemini_review_enabled"] == "true"


def test_the_review_field_defaults_to_off_and_offers_it_first():
    """A select falls back to choices[0] when there is no current value."""
    from onboard.config import FIELDS_BY_KEY
    field = FIELDS_BY_KEY["GEMINI_REVIEW_ENABLED"]
    assert field.default == "false"
    assert field.choices[0] == "false"


def test_install_config_falls_back_to_review_off(tmp_path, monkeypatch):
    """apply_install_config carries its own copy of the default."""
    import sqlite3
    import onboard.actions as actions
    from onboard.executor import Executor, NullReporter
    db = tmp_path / "mounted" / "data" / "tubematic.db"
    db.parent.mkdir(parents=True)
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.commit()
    con.close()
    monkeypatch.setattr(actions, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(actions, "DB_PATH", db)
    cfg = type("Cfg", (), {"values": {"OPENAI_API_KEY": "o"}})()
    actions.apply_install_config(cfg, Executor(dry_run=False), NullReporter())
    con = sqlite3.connect(db)
    row = con.execute("SELECT value FROM settings WHERE key='gemini_review_enabled'").fetchone()
    con.close()
    assert row[0] == "false"


@pytest.mark.parametrize("raw,expected", [("0", "1"), ("-5", "1"), ("99", "24")])
def test_seeding_clamps_an_out_of_range_fps(tmp_path, raw, expected):
    rows = _seed_and_read(tmp_path, {"ai_review_fps": raw})
    assert rows["ai_review_fps"] == expected


@pytest.mark.parametrize("raw,expected", [("0", "1"), ("7", "2")])
def test_seeding_clamps_an_out_of_range_loop_cap(tmp_path, raw, expected):
    rows = _seed_and_read(tmp_path, {"ai_review_max_loops": raw})
    assert rows["ai_review_max_loops"] == expected


@pytest.mark.parametrize("raw", ["not-a-number", ""])
def test_seeding_falls_back_to_defaults_on_unparseable_values(tmp_path, raw):
    rows = _seed_and_read(tmp_path, {"ai_review_fps": raw, "ai_review_max_loops": raw})
    assert rows["ai_review_fps"] == "10"
    assert rows["ai_review_max_loops"] == "1"


def test_seeding_rejects_an_unknown_model_rather_than_storing_it(tmp_path):
    """An image model or a typo here would 400 on every review — which fails
    open, so videos would ship unreviewed with nothing in the log."""
    rows = _seed_and_read(tmp_path, {"ai_review_model": "gemini-2.5-flash-image"})
    assert rows["ai_review_model"] == DEFAULT_AI_REVIEW_MODEL


def test_prefill_reads_a_stored_value_back(tmp_path):
    """A re-run of the step must show what is currently configured, not the
    field default — otherwise re-onboarding silently resets the model."""
    from onboard import config as config_module

    db = tmp_path / "tubematic.db"
    con = sqlite3.connect(str(db))
    con.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute("INSERT INTO settings VALUES ('ai_review_model', 'gemini-3.5-flash')")
    con.execute("INSERT INTO settings VALUES ('ai_review_fps', '4')")
    con.commit()
    con.close()

    values = config_module.load_current_values(repo_root=tmp_path, db_path=db)
    assert values["ai_review_model"] == "gemini-3.5-flash"
    assert values["ai_review_fps"] == "4"
