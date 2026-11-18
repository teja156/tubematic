"""Every bind volume in docker-compose.yml has its folder created by the
directories step and its device re-pointed by the volume reconcile (TMDEV-242).

Docker does not create the device folder of a `local` bind volume: a missing one
fails the mount ("no such file or directory"). An upgrade from a release
without a folder (the code sandbox's `sandbox`, v2.3.0) reaches the compose
`up` through stack.start, whose first step is apply_directories, so the folder
list is what keeps an old install from failing to start.
"""
from pathlib import Path

import yaml

import onboard.actions as actions
from onboard.config import DATA_SUBDIRS
from onboard.executor import Executor, NullReporter

COMPOSE = yaml.safe_load((Path(__file__).resolve().parents[2] / "docker-compose.yml").read_text())
PREFIX = "${HOME}/.tubematic-data/"


def _bind_subdirs():
    return {name: v["driver_opts"]["device"][len(PREFIX):] for name, v in COMPOSE["volumes"].items()
            if v.get("driver_opts", {}).get("device", "").startswith(PREFIX)}


def test_every_compose_bind_volume_has_a_folder_the_directories_step_creates():
    assert set(_bind_subdirs().values()) <= set(DATA_SUBDIRS)


def test_every_compose_bind_volume_is_in_the_reconcile_map():
    expected = {f"tubematic_{name}": sub for name, sub in _bind_subdirs().items()}
    assert actions._VOLUME_DEVICES == expected


def test_the_directories_step_creates_the_sandbox_spool_on_an_upgrade(tmp_path, monkeypatch):
    """A v2.2 data root has no sandbox/ folder."""
    import onboard.config as config
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    for d in ("jobs", "data", "output_videos", "scenes/generated", "logs", "backups"):
        (tmp_path / d).mkdir(parents=True)
    assert not (tmp_path / "sandbox").exists()
    actions.apply_directories(None, Executor(dry_run=False), NullReporter())
    assert (tmp_path / "sandbox").is_dir()


def test_the_directories_step_creates_the_styles_folder_on_an_upgrade(tmp_path, monkeypatch):
    """A v2.3 data root has no styles/ folder, and compose cannot bind one that is missing."""
    import onboard.config as config
    monkeypatch.setattr(config, "DATA_ROOT", tmp_path)
    for d in ("jobs", "data", "output_videos", "scenes/generated", "logs", "backups", "sandbox"):
        (tmp_path / d).mkdir(parents=True)
    actions.apply_directories(None, Executor(dry_run=False), NullReporter())
    assert (tmp_path / "styles").is_dir()


def test_the_release_smoke_test_creates_every_data_folder():
    """release.yml's smoke job skips onboarding and creates the folders itself, so a
    new bind volume that its list misses fails `up` at publish time, not in CI."""
    import re
    from pathlib import Path
    workflow = (Path(__file__).resolve().parents[2] / ".github" / "workflows" / "release.yml").read_text()
    made = set(re.findall(r'"\$HOME/\.tubematic-data/([a-z_/]+)"', workflow))
    assert set(DATA_SUBDIRS) <= made, sorted(set(DATA_SUBDIRS) - made)
