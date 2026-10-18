import sys
from pathlib import Path

# Repo root two levels up from this file (onboard/tests/conftest.py -> onboard/ -> repo root).
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_poll_registry(tmp_path, monkeypatch):
    """The stop/upgrade gate reads the poller's session registry under
    ~/.tubematic-agent (TMDEV-129). A test must never see a real one — on a
    machine running Tubematic it could hold live entries."""
    from onboard import stack
    monkeypatch.setattr(stack, "SESSIONS_REGISTRY", tmp_path / "poll-sessions.json")


@pytest.fixture(autouse=True)
def _no_real_secrets(tmp_path, monkeypatch):
    """Service tokens resolve to ~/.tubematic-data/secrets by default (TMDEV-152).
    Starting the stack creates any that are missing, so a test that runs a real
    Executor through it would otherwise write tokens into the host's home."""
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(tmp_path / "secrets"))
