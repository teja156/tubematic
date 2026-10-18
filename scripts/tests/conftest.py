"""Keep every poll.py test away from the real supervisor state files.

The heartbeat, the session registry and the agent output files all live beside
the real poll lock under ~/.tubematic-agent (TMDEV-129). A test that wrote
there could make a real cron-invoked supervisor adopt a process that does not
exist, or report a fake stale heartbeat.
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


@pytest.fixture(autouse=True)
def _poll_state_in_tmp(tmp_path, monkeypatch):
    # Service tokens resolve to ~/.tubematic-data/secrets by default (TMDEV-152),
    # and starting the stack creates any that are missing.
    monkeypatch.setenv("TUBEMATIC_SECRETS_DIR", str(tmp_path / "secrets"))
    # poll.main() refuses to run without an API token, so give it one.
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
    from tubematic_core.auth import ensure_secrets
    ensure_secrets(tmp_path / "secrets")
    import poll
    monkeypatch.setattr(poll, "HEARTBEAT", tmp_path / "poll.heartbeat")
    monkeypatch.setattr(poll, "REGISTRY", tmp_path / "poll-sessions.json")
    monkeypatch.setattr(poll, "SESSIONS_DIR", tmp_path / "sessions")
    # service.py's gate reads the same registry through onboard/stack.py.
    try:
        from onboard import stack
    except ImportError:
        return
    monkeypatch.setattr(stack, "SESSIONS_REGISTRY", tmp_path / "poll-sessions.json")
