"""Source checkout vs. release tarball (TMDEV-91 Phase 2).

A release tarball ships no source trees to build from — it deliberately has
no renderer/Dockerfile — so `onboard.py` has to know not to `docker compose
build` against a tree that isn't there, and to skip the Node/npx prereqs a
local build would need. Detection is auto (release when renderer/Dockerfile
is absent) with an explicit --install-mode escape hatch, and the resolved
mode is both printed to the user and recorded in .onboard-state.json so a
later "why didn't my change get rebuilt?" can be answered from disk.

Every assertion here goes through the executor's dry-run recording
(onboard/executor.py) or captured console output — never real Docker, per
`onboard/tests/test_renderer_step.py`'s established pattern.
"""
import io
import json
import subprocess
from unittest.mock import patch

import pytest
from rich.console import Console

import onboard.actions as actions
from onboard.config import OnboardConfig, detect_install_mode, resolve_install_mode
from onboard.executor import Executor, NullReporter


class _Rep(NullReporter):
    def __init__(self):
        self.oks, self.warns, self.fails, self.infos = [], [], [], []
        self.fail_hints = []
    def ok(self, msg, *a, **k): self.oks.append(msg)
    def warn(self, msg, *a, **k): self.warns.append(msg)
    def fail(self, msg, hint="", *a, **k):
        self.fails.append(msg)
        self.fail_hints.append(hint)
    def info(self, msg, *a, **k): self.infos.append(msg)


@pytest.fixture
def no_volume_reconcile(monkeypatch):
    monkeypatch.setattr(actions, "_reconcile_volume_devices", lambda ex, rep: None)


# ── Detection ────────────────────────────────────────────────────────────

def test_release_mode_is_detected_when_there_is_no_dockerfile(tmp_path):
    """The tarball's defining feature: no source trees, so no Dockerfile."""
    assert detect_install_mode(tmp_path) == "release"


def test_dev_mode_is_detected_in_a_git_checkout():
    """This worktree is a real checkout, so it has renderer/Dockerfile."""
    assert detect_install_mode() == "dev"


def test_an_explicit_flag_overrides_detection(tmp_path):
    """tmp_path has no Dockerfile — auto-detect alone would say release."""
    assert resolve_install_mode("dev", repo_root=tmp_path) == "dev"
    assert resolve_install_mode(None, repo_root=tmp_path) == "release"


def test_recorded_state_is_used_when_no_flag_is_given(tmp_path):
    """A later `--step renderer` inside this same checkout has no flag, and
    detection alone would say "dev" every time (this worktree always has
    renderer/Dockerfile) — the whole reason release mode was recorded in the
    first place would be lost. `repo_root` here is this real checkout, i.e.
    detection alone would say "dev"; the recorded "release" must win."""
    assert resolve_install_mode(None, recorded="release") == "release"


def test_an_explicit_flag_overrides_a_recorded_mode(tmp_path):
    """A one-off --install-mode dev must not be shadowed by a prior release
    install's recorded state."""
    assert resolve_install_mode("dev", recorded="release") == "dev"


def test_no_recorded_state_falls_back_to_detection(tmp_path):
    assert resolve_install_mode(None, recorded=None, repo_root=tmp_path) == "release"


# ── apply_renderer / apply_dashboard: actions, not the compose file ────────

def test_release_mode_never_shells_out_to_build(no_volume_reconcile):
    """The whole point: a release install has no source tree to build from."""
    cfg = OnboardConfig(values={"install_mode": "release"})

    ex = Executor(dry_run=True)
    actions.apply_renderer(cfg, ex, _Rep())
    assert not any("build" in i.detail for i in ex.intents), ex.intents

    ex2 = Executor(dry_run=True)
    actions.apply_dashboard(cfg, ex2, _Rep())
    assert not any("build" in i.detail for i in ex2.intents), ex2.intents


def test_release_mode_pulls_before_up(no_volume_reconcile):
    cfg = OnboardConfig(values={"install_mode": "release"})

    ex = Executor(dry_run=True)
    actions.apply_renderer(cfg, ex, _Rep())
    runs = [i.detail for i in ex.intents if i.kind == "run"]
    pull_idx = next(i for i, d in enumerate(runs) if "pull" in d)
    up_idx = next(i for i, d in enumerate(runs) if d.startswith("docker compose up"))
    assert pull_idx < up_idx, runs

    ex2 = Executor(dry_run=True)
    actions.apply_dashboard(cfg, ex2, _Rep())
    runs2 = [i.detail for i in ex2.intents if i.kind == "run"]
    pull_idx2 = next(i for i, d in enumerate(runs2) if "pull" in d)
    up_idx2 = next(i for i, d in enumerate(runs2) if d.startswith("docker compose up"))
    assert pull_idx2 < up_idx2, runs2


def _fake_run(fail_on, stderr=""):
    def _run(argv, cwd=None):
        rc = 1 if fail_on in argv else 0
        return subprocess.CompletedProcess(argv, rc, "", stderr if rc else "")
    return _run


def test_a_failed_pull_shows_dockers_reason_not_an_empty_log(no_volume_reconcile):
    """A failed `docker compose pull` creates no container, so `docker
    compose logs` (the build-path hint this used to copy-paste) prints
    nothing at all. The images are public, so the hint is docker's own reason
    plus where to look -- never an instruction to log in."""
    cfg = OnboardConfig(values={"install_mode": "release"})
    reason = "manifest for ghcr.io/x/tubematic-backend:9.9.9 not found"

    ex = Executor(dry_run=False)
    ex.run = _fake_run("pull", reason)
    rep = _Rep()
    actions.apply_renderer(cfg, ex, rep)
    assert any(reason in h and "ghcr.io" in h for h in rep.fail_hints), rep.fail_hints
    assert not any("docker login" in h for h in rep.fail_hints), rep.fail_hints
    assert not any("compose logs" in h for h in rep.fail_hints), rep.fail_hints

    ex2 = Executor(dry_run=False)
    ex2.run = _fake_run("pull")
    rep2 = _Rep()
    actions.apply_dashboard(cfg, ex2, rep2)
    assert any("ghcr.io" in h for h in rep2.fail_hints), rep2.fail_hints
    assert not any("docker login" in h for h in rep2.fail_hints), rep2.fail_hints
    assert not any("compose logs" in h for h in rep2.fail_hints), rep2.fail_hints


def test_dev_mode_still_builds_exactly_as_before(no_volume_reconcile):
    """Regression guard — the existing install flow must be untouched."""
    ex = Executor(dry_run=True)
    actions.apply_renderer(None, ex, _Rep())
    builds = [i.detail for i in ex.intents if i.kind == "run" and "build" in i.detail]
    assert len(builds) == 1
    assert "tubematic-api" in builds[0]
    assert not any("pull" in i.detail for i in ex.intents)

    ex2 = Executor(dry_run=True)
    actions.apply_dashboard(None, ex2, _Rep())
    builds2 = [i.detail for i in ex2.intents if i.kind == "run" and "build" in i.detail]
    assert len(builds2) == 1
    assert "tubematic-dashboard" in builds2[0]
    assert not any("pull" in i.detail for i in ex2.intents)


# ── Prerequisites ────────────────────────────────────────────────────────

def test_prerequisites_does_not_require_node_in_release_mode():
    from onboard.checks import check_prerequisites
    items = check_prerequisites(mode="release")
    assert not any("Node" in i.label or "npx" in i.label for i in items), items


@pytest.mark.parametrize("version, ok", [
    ("v22.0.0", False),   # major 22 alone is not enough: the installer needs 22.20
    ("v22.19.9", False),
    ("v22.20.0", True),
    ("v24.1.0", True),
    ("v18.19.1", False),
    ("garbage", False),
])
def test_the_node_check_compares_major_and_minor(monkeypatch, version, ok):
    from onboard import checks
    monkeypatch.setattr(checks, "_run",
                        lambda cmd: subprocess.CompletedProcess(cmd, 0, version, ""))
    monkeypatch.setattr(checks.shutil, "which", lambda name: f"/usr/bin/{name}")
    [node] = [i for i in checks.check_prerequisites(mode="dev") if i.label.startswith("Node.js")]
    assert node.ok is ok
    assert node.severity == "warning"  # never blocks onboarding


# ── Reporting + persistence ─────────────────────────────────────────────

def test_the_resolved_mode_is_reported_to_the_user():
    buf = io.StringIO()
    with patch("onboard.plain.console", Console(file=buf, width=200)), \
         patch("onboard.plain.check_prerequisites", return_value=[]) as mock_prereq, \
         patch("onboard.plain.check_installation", return_value={"SERVICES": [], "AGENT": []}):
        from onboard import plain
        plain.run_wizard(dry_run=True, step_key="prerequisites", install_mode="release")
    assert mock_prereq.called, "the stub was never exercised — patch target is inert"
    out = buf.getvalue()
    assert "release" in out.lower()


def test_the_resolved_mode_is_recorded_in_the_state_file(tmp_path, monkeypatch):
    import onboard.state as state_mod
    state_file = tmp_path / ".onboard-state.json"
    monkeypatch.setattr(state_mod, "STATE_FILE", state_file)

    with patch("onboard.plain.check_prerequisites", return_value=[]) as mock_prereq, \
         patch("onboard.plain.check_installation", return_value={"SERVICES": [], "AGENT": []}):
        from onboard import plain
        plain.run_wizard(dry_run=False, step_key="prerequisites", install_mode="release")
    assert mock_prereq.called, "the stub was never exercised — patch target is inert"

    saved = json.loads(state_file.read_text())
    assert saved.get("install_mode") == "release"


def test_a_later_step_with_no_flag_reuses_the_recorded_mode(tmp_path, monkeypatch):
    """The regression this whole group exists for: `onboard.py --install-mode
    release` records the mode, and a later `onboard.py --step renderer` (no
    flag) must not silently re-detect. This worktree is a real dev checkout
    (it has renderer/Dockerfile), so live detection alone would say "dev" —
    if the second call reports "dev" here, the recorded state was ignored."""
    import onboard.state as state_mod
    state_file = tmp_path / ".onboard-state.json"
    monkeypatch.setattr(state_mod, "STATE_FILE", state_file)

    with patch("onboard.plain.check_prerequisites", return_value=[]) as mock_prereq, \
         patch("onboard.plain.check_installation", return_value={"SERVICES": [], "AGENT": []}):
        from onboard import plain
        plain.run_wizard(dry_run=False, step_key="prerequisites", install_mode="release")

        buf = io.StringIO()
        with patch("onboard.plain.console", Console(file=buf, width=200)):
            plain.run_wizard(dry_run=True, step_key="prerequisites", install_mode=None)
    assert mock_prereq.called, "the stub was never exercised — patch target is inert"

    out = buf.getvalue().lower()
    assert "release" in out
    assert "recorded" in out
    assert "release install" in out  # the release-only hint line, not printed for "dev"


def test_an_explicit_flag_still_overrides_a_recorded_mode_end_to_end(tmp_path, monkeypatch):
    import onboard.state as state_mod
    state_file = tmp_path / ".onboard-state.json"
    monkeypatch.setattr(state_mod, "STATE_FILE", state_file)

    with patch("onboard.plain.check_prerequisites", return_value=[]) as mock_prereq, \
         patch("onboard.plain.check_installation", return_value={"SERVICES": [], "AGENT": []}):
        from onboard import plain
        plain.run_wizard(dry_run=False, step_key="prerequisites", install_mode="release")

        buf = io.StringIO()
        with patch("onboard.plain.console", Console(file=buf, width=200)):
            plain.run_wizard(dry_run=True, step_key="prerequisites", install_mode="dev")
    assert mock_prereq.called, "the stub was never exercised — patch target is inert"

    out = buf.getvalue().lower()
    assert "release install" not in out  # the release-only hint must not fire for dev
    saved = json.loads(state_file.read_text())
    assert saved.get("install_mode") == "release", (
        "a dry-run explicit override must not overwrite the recorded state"
    )
