"""Step-order invariants: build/container-start steps must be last, and
directories/database must precede them (Docker creates missing bind-mount
targets as root otherwise)."""
from onboard.steps import DEFAULT_STEPS, STEP_DEFS, VALID_KEYS


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


def test_build_steps_are_the_last_two_of_a_full_install():
    keys = [s.key for s in DEFAULT_STEPS]
    assert keys[-2:] == ["renderer", "dashboard"]


def test_no_step_after_dashboard_builds_or_starts():
    dashboard_idx = _index("dashboard")
    for step in STEP_DEFS[dashboard_idx + 1:]:
        assert not step.builds_or_starts


def test_step_keys_are_unique():
    keys = [s.key for s in STEP_DEFS]
    assert len(keys) == len(set(keys))


def test_eleven_steps_in_the_default_flow():
    assert len(DEFAULT_STEPS) == 11


def test_the_renderers_step_is_opt_in_and_the_only_one():
    """Publishing the render gateway to other machines changes what a working
    install exposes, so a full install never does it (TMDEV-190)."""
    assert [s.key for s in STEP_DEFS if s.opt_in] == ["renderers"]
    assert "renderers" not in {s.key for s in DEFAULT_STEPS}
    assert "renderers" in VALID_KEYS


def test_opt_in_steps_come_after_the_full_install():
    """--steps numbers them after every step a full install runs."""
    keys = [s.key for s in STEP_DEFS]
    assert keys[:len(DEFAULT_STEPS)] == [s.key for s in DEFAULT_STEPS]


def test_the_gpu_step_precedes_the_renderer_step():
    """The GPU override must exist before the first `up` creates the renderer,
    or a fresh install starts on the CPU and needs a recreate (TMDEV-178)."""
    keys = [s.key for s in STEP_DEFS]
    assert keys.index("gpu") == keys.index("renderer") - 1


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
