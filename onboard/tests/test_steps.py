"""Step-order invariants: build/container-start steps must be last, and
directories/database must precede them (Docker creates missing bind-mount
targets as root otherwise)."""
from onboard.steps import STEP_DEFS, VALID_KEYS


def _index(key: str) -> int:
    return next(i for i, s in enumerate(STEP_DEFS) if s.key == key)


def test_directories_and_database_precede_container_steps():
    assert _index("directories") < _index("renderer")
    assert _index("directories") < _index("dashboard")
    assert _index("database") < _index("renderer")
    assert _index("database") < _index("dashboard")


def test_only_renderer_and_dashboard_build_or_start():
    build_keys = {s.key for s in STEP_DEFS if s.builds_or_starts}
    assert build_keys == {"renderer", "dashboard"}


def test_build_steps_are_the_last_two():
    keys = [s.key for s in STEP_DEFS]
    assert keys[-2:] == ["renderer", "dashboard"]


def test_no_step_after_dashboard_builds_or_starts():
    dashboard_idx = _index("dashboard")
    for step in STEP_DEFS[dashboard_idx + 1:]:
        assert not step.builds_or_starts


def test_step_keys_are_unique():
    keys = [s.key for s in STEP_DEFS]
    assert len(keys) == len(set(keys))


def test_ten_steps_in_the_default_flow():
    assert len(STEP_DEFS) == 10


def test_the_auth_step_precedes_every_container_step():
    """Compose refuses to start a service whose token file is missing, and the
    password is in the database the database step creates."""
    keys = [s.key for s in STEP_DEFS]
    assert keys.index("database") < keys.index("auth") < keys.index("renderer")
    assert keys.index("auth") < keys.index("dashboard")


def test_agent_setup_is_not_a_step():
    """Agents are installed by --install-agent after the project (TMDEV-90)."""
    assert "claude" not in VALID_KEYS


def test_every_step_is_addressable_by_step():
    """--step must resolve every step, or one would be unreachable."""
    assert {s.key for s in STEP_DEFS} == VALID_KEYS
