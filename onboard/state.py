"""Onboard progress state — .onboard-state.json load/save/mark.

Tracks which apply-phase steps have completed so re-runs can skip them.
"""
import json
from datetime import datetime
from pathlib import Path

from onboard.config import REPO_ROOT

STATE_FILE = REPO_ROOT / ".onboard-state.json"

# Steps whose output is a *derived artifact* built from configuration rather
# than a one-time action: the cron line embeds the agent binary and workspace
# path, and the containers embed the compose file. TMDEV-73 moved the inputs
# for both out of .env, so a pre-migration install has to rebuild them even
# though it already ran these steps once.
_DERIVED_STEPS = ("cron", "renderer", "dashboard")

# Steps that no longer exist under any name. `transcripts` and `script_skill`
# were merged into an on-demand `script_profiles` step by TMDEV-79; TMDEV-81
# retired that too, moving profile creation to the dashboard. `script_profiles`
# was never written to state (it was on-demand for its whole life), so only the
# two original keys can be present. `claude` left the default flow in TMDEV-90:
# agents are installed separately, by `onboard.py --install-agent <name>`,
# which records its state in the agents table rather than here.
_RETIRED_STEPS = ("transcripts", "script_skill", "script_profiles", "claude")


def _migrate(state: dict) -> dict:
    """Bring a pre-TMDEV-73 state file forward.

    The `env` step became `install_config`, so it re-runs on its own — an
    absent key is simply not done. What needs clearing is the derived steps
    above, which are marked done but were built from a .env that no longer
    feeds anything. No version marker needed: the presence of `env` alongside
    the absence of `install_config` *is* the marker, and it is self-clearing.
    """
    if "env" in state and "install_config" not in state:
        state.pop("env", None)
        for key in _DERIVED_STEPS:
            state.pop(key, None)
    # Retired-step entries are inert but would show up in --status as steps
    # that no longer exist. Popped unconditionally, not inside the branch
    # above: a pre-TMDEV-73 state file has both problems, a newer one has only
    # this one.
    for key in _RETIRED_STEPS:
        state.pop(key, None)
    return state


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return _migrate(json.loads(STATE_FILE.read_text()))
        except Exception:
            return {}
    return {}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def is_done(state: dict, key: str) -> bool:
    return state.get(key, {}).get("done", False)


def mark_done(state: dict, key: str) -> None:
    state[key] = {"done": True, "ts": datetime.now().strftime("%Y-%m-%d %H:%M")}
