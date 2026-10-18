"""Bringing a pre-TMDEV-73 .onboard-state.json forward.

The `env` step became `install_config`, which re-runs on its own because an
absent key is simply not done. The problem is the *derived* steps: cron and the
two container steps are marked done but were built from a .env that no longer
feeds anything, so they have to be rebuilt.
"""
from onboard.state import _DERIVED_STEPS, _RETIRED_STEPS, _migrate


def _legacy(**extra):
    state = {
        "env": {"done": True, "ts": "2026-01-01 00:00"},
        "database": {"done": True, "ts": "2026-01-01 00:00"},
        "cron": {"done": True, "ts": "2026-01-01 00:00"},
        "renderer": {"done": True, "ts": "2026-01-01 00:00"},
        "dashboard": {"done": True, "ts": "2026-01-01 00:00"},
    }
    state.update(extra)
    return state


def test_drops_the_retired_env_marker():
    assert "env" not in _migrate(_legacy())


def test_clears_every_derived_step():
    migrated = _migrate(_legacy())
    for key in _DERIVED_STEPS:
        assert key not in migrated, f"{key} must be rebuilt from the settings table"


def test_leaves_unrelated_steps_alone():
    """Only the artifacts built from .env need redoing — re-running the schema
    init or a skill copy for everyone would be gratuitous."""
    migrated = _migrate(_legacy())
    assert migrated["database"]["done"] is True


def test_the_retired_claude_step_is_dropped():
    """It left the default flow for --install-agent (TMDEV-90). A leftover
    entry would show in --status as a step that no longer exists."""
    migrated = _migrate({"install_config": {"done": True, "ts": "x"},
                         "claude": {"done": True, "ts": "x"}})
    assert "claude" not in migrated
    assert migrated["install_config"]["done"] is True


def test_a_fresh_state_is_untouched():
    assert _migrate({}) == {}


def test_a_post_migration_state_is_untouched():
    """The presence of `env` alongside the absence of `install_config` is the
    marker, so it self-clears — no version field needed."""
    already = {
        "install_config": {"done": True, "ts": "x"},
        "cron": {"done": True, "ts": "x"},
    }
    assert _migrate(dict(already)) == already


def test_is_idempotent():
    once = _migrate(_legacy())
    assert _migrate(dict(once)) == once


def test_a_half_migrated_state_is_left_alone():
    """Both markers present means install_config already ran; re-clearing cron
    would loop the user through the container builds on every launch."""
    state = _legacy(install_config={"done": True, "ts": "x"})
    assert _migrate(dict(state))["cron"]["done"] is True


# ── Retired steps: transcripts / script_skill / script_profiles ────────────

def test_drops_the_retired_transcript_steps_from_a_legacy_state():
    migrated = _migrate(_legacy(**{
        "transcripts": {"done": True, "ts": "2026-01-01 00:00"},
        "script_skill": {"done": True, "ts": "2026-01-01 00:00"},
    }))
    for key in _RETIRED_STEPS:
        assert key not in migrated


def test_drops_them_from_a_modern_state_too():
    """The pop is unconditional, not folded into the `env` branch: a
    post-TMDEV-73 state file has these keys but no `env` marker to trigger it."""
    modern = {
        "install_config": {"done": True, "ts": "2026-01-01 00:00"},
        "transcripts": {"done": True, "ts": "2026-01-01 00:00"},
        "script_skill": {"done": True, "ts": "2026-01-01 00:00"},
        "cron": {"done": True, "ts": "2026-01-01 00:00"},
    }
    migrated = _migrate(dict(modern))
    assert "transcripts" not in migrated
    assert "script_skill" not in migrated
    # ...and it must not take the derived-step reset with it.
    assert migrated["cron"]["done"] is True
    assert migrated["install_config"]["done"] is True


def test_script_profiles_is_dropped_too():
    """TMDEV-81 retired the on-demand script_profiles step — profiles are built
    from the dashboard now. It was never written to state (it was on-demand for
    its whole life), so this only matters for a hand-edited file, but leaving it
    would show a step that no longer exists in --status."""
    migrated = _migrate({"install_config": {"done": True, "ts": "2026-01-01 00:00"},
                         "script_profiles": {"done": True, "ts": "2026-01-01 00:00"}})
    assert "script_profiles" not in migrated
    assert migrated["install_config"]["done"] is True
