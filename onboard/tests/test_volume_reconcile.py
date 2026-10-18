"""Named volumes must be recreated when their bind device moves (TMDEV-76).

Docker fixes a named volume's driver_opts at creation. Editing
docker-compose.yml does not move an existing one — Compose notices and
*prompts*, and onboarding runs it non-interactively, so the prompt defaults to
no and the stack silently keeps mounting the old path. Verified directly
against Docker before writing this.
"""
import subprocess

import pytest

import onboard.actions as actions
from onboard.config import DATA_ROOT
from onboard.executor import Executor, NullReporter


class _Rep(NullReporter):
    def __init__(self):
        self.warns, self.fails = [], []
    def warn(self, msg, *a, **k): self.warns.append(msg)
    def fail(self, msg, *a, **k): self.fails.append(msg)


def _inspect_returning(devices: dict):
    """Stub `docker volume inspect`, returning a device per volume name."""
    def run(cmd, **kw):
        name = cmd[3]
        if name in devices:
            return subprocess.CompletedProcess(cmd, 0, devices[name] + "\n", "")
        return subprocess.CompletedProcess(cmd, 1, "", "no such volume")
    return run


def test_no_volumes_yet_is_a_no_op(monkeypatch):
    monkeypatch.setattr(actions.subprocess, "run", _inspect_returning({}))
    ex = Executor(dry_run=True)
    actions._reconcile_volume_devices(ex, _Rep())
    assert ex.intents == []


def test_matching_devices_are_left_alone(monkeypatch):
    devices = {name: str(DATA_ROOT / sub) for name, sub in actions._VOLUME_DEVICES.items()}
    monkeypatch.setattr(actions.subprocess, "run", _inspect_returning(devices))
    ex = Executor(dry_run=True)
    actions._reconcile_volume_devices(ex, _Rep())
    assert ex.intents == []


def test_a_stale_device_is_removed_and_reported(monkeypatch):
    """The upgrade case: volumes created against the old repo-relative tree."""
    devices = {name: f"/home/someone/tubematic/mounted/{sub}"
               for name, sub in actions._VOLUME_DEVICES.items()}
    monkeypatch.setattr(actions.subprocess, "run", _inspect_returning(devices))
    ex = Executor(dry_run=True)
    rep = _Rep()
    actions._reconcile_volume_devices(ex, rep)

    details = [i.detail for i in ex.intents]
    # Containers are brought down first — a volume in use cannot be removed.
    assert any("compose" in d and "down" in d for d in details)
    for name in actions._VOLUME_DEVICES:
        assert any(f"volume rm {name}" in d or name in d for d in details)
    assert rep.warns and "previous data location" in rep.warns[0]


def test_only_the_mismatched_volumes_are_touched(monkeypatch):
    devices = {name: str(DATA_ROOT / sub) for name, sub in actions._VOLUME_DEVICES.items()}
    devices["tubematic_db-data"] = "/somewhere/else/data"
    monkeypatch.setattr(actions.subprocess, "run", _inspect_returning(devices))
    ex = Executor(dry_run=True)
    actions._reconcile_volume_devices(ex, _Rep())

    details = " ".join(i.detail for i in ex.intents)
    assert "tubematic_db-data" in details
    assert "tubematic_output-videos" not in details


def test_dry_run_removes_nothing(monkeypatch):
    """The destructive half must be a recorded intent, not an action."""
    devices = {name: "/old/path" for name in actions._VOLUME_DEVICES}
    monkeypatch.setattr(actions.subprocess, "run", _inspect_returning(devices))
    ex = Executor(dry_run=True)
    actions._reconcile_volume_devices(ex, _Rep())
    assert all(i.kind == "run" for i in ex.intents)
