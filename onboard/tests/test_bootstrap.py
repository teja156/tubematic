"""The venv bootstrap every operator entry point runs first (onboard/bootstrap.py).

This is the only code that runs before anything can be imported, on a machine
nothing has been installed on yet, so its two failure messages are the whole
user interface for a broken Python. Debian and Ubuntu ship `venv` with the
base interpreter but package pip's bootstrap (`ensurepip`) separately, which
makes both failures routine on a fresh server and neither of them obvious:
`python3 -m venv` creates the directory, fails at the pip step, and leaves an
interpreter with no pip beside it.

Nothing here runs a real `python -m venv` or `pip install`: both are patched,
so the tests assert on what the user is told and on which argv was attempted.
"""
import subprocess
import sys

import pytest

from onboard import bootstrap


def _fake_venv(venv_dir, *, with_pip: bool) -> None:
    """What `python -m venv` leaves behind, with or without a seeded pip."""
    (venv_dir / "bin").mkdir(parents=True, exist_ok=True)
    (venv_dir / "bin" / "python3").touch()
    if with_pip:
        (venv_dir / "bin" / "pip3").touch()


@pytest.fixture
def at(monkeypatch, tmp_path):
    """Point bootstrap at a throwaway install directory."""
    monkeypatch.setattr(bootstrap, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["onboard.py", "--step", "database"])
    return tmp_path


# ── ensurepip detection ──────────────────────────────────────────────────

def test_a_missing_ensurepip_is_detected(monkeypatch):
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda name: None if name == "ensurepip" else object())
    assert bootstrap._ensurepip_missing() is True


def test_a_present_ensurepip_is_not_reported_missing(monkeypatch):
    import importlib.util
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: object())
    assert bootstrap._ensurepip_missing() is False


# ── A venv with no pip in it ─────────────────────────────────────────────

def test_a_venv_without_pip_is_created_again(at, monkeypatch):
    """The second half of the Debian defect: a failed ensurepip leaves
    bin/python3 on disk. Keying readiness on the interpreter alone made the
    next run re-exec into that venv and fail at the first pip call instead,
    reporting the same cause as a different problem."""
    _fake_venv(at / ".venv", with_pip=False)
    attempted = []

    def fake_run(cmd, check=False):
        attempted.append(cmd)
        _fake_venv(at / ".venv", with_pip=True)   # the package is installed now
        return subprocess.CompletedProcess(cmd, 0)

    monkeypatch.setattr(bootstrap.subprocess, "run", fake_run)
    execs = []
    monkeypatch.setattr(bootstrap.os, "execv", lambda path, argv: execs.append(argv))

    bootstrap.ensure_venv(at / "onboard.py")

    assert attempted, "a pip-less venv must be created again, not re-used"
    assert attempted[0][1:3] == ["-m", "venv"]
    assert execs, "and only then re-exec into it"
    assert execs[0][2:] == ["--step", "database"]   # the caller's own flags survive


def test_a_complete_venv_is_re_used_without_creating_anything(at, monkeypatch):
    _fake_venv(at / ".venv", with_pip=True)
    monkeypatch.setattr(bootstrap.subprocess, "run",
                        lambda *a, **k: pytest.fail("an existing venv must not be rebuilt"))
    execs = []
    monkeypatch.setattr(bootstrap.os, "execv", lambda path, argv: execs.append(argv))
    bootstrap.ensure_venv(at / "onboard.py")
    assert execs


# ── What the user is told when creation fails ────────────────────────────

def _fail_creation(monkeypatch):
    monkeypatch.setattr(bootstrap.subprocess, "run",
                        lambda cmd, check=False: subprocess.CompletedProcess(cmd, 1))


def test_the_failure_hint_names_the_apt_package_when_ensurepip_is_missing(
        at, monkeypatch, capsys):
    _fail_creation(monkeypatch)
    monkeypatch.setattr(bootstrap, "_ensurepip_missing", lambda: True)

    with pytest.raises(SystemExit) as exit_info:
        bootstrap.ensure_venv(at / "onboard.py")

    assert exit_info.value.code == 1
    out = capsys.readouterr().out
    assert "apt install python3-venv" in out
    # Repeating the command that just failed is the defect: it fails
    # identically, with the same message, and names nothing to install.
    assert "python3 -m venv" not in out


def test_the_failure_hint_stays_generic_when_ensurepip_is_present(at, monkeypatch, capsys):
    _fail_creation(monkeypatch)
    monkeypatch.setattr(bootstrap, "_ensurepip_missing", lambda: False)

    with pytest.raises(SystemExit):
        bootstrap.ensure_venv(at / "onboard.py")

    out = capsys.readouterr().out
    assert "python3 -m venv" in out
    assert "apt" not in out, "do not send someone to apt for an unrelated failure"


def test_a_venv_that_comes_back_without_pip_is_a_failure(at, monkeypatch, capsys):
    """A zero exit code is not enough: Debian's venv can report success for
    the directory and still seed no pip."""
    monkeypatch.setattr(bootstrap.subprocess, "run",
                        lambda cmd, check=False: (_fake_venv(at / ".venv", with_pip=False)
                                                  or subprocess.CompletedProcess(cmd, 0)))
    monkeypatch.setattr(bootstrap.os, "execv",
                        lambda path, argv: pytest.fail("must not re-exec into a pip-less venv"))
    with pytest.raises(SystemExit):
        bootstrap.ensure_venv(at / "onboard.py")


# ── ensure_deps ──────────────────────────────────────────────────────────

def test_the_dependency_install_failure_names_the_apt_package(monkeypatch, capsys):
    """The same cause reaches ensure_deps when someone activates a pip-less
    venv by hand, where the bare "pip install failed" says nothing useful."""
    monkeypatch.setitem(sys.modules, "rich", None)   # makes `import rich` raise
    monkeypatch.setattr(bootstrap, "_ensurepip_missing", lambda: True)
    monkeypatch.setattr(bootstrap.subprocess, "run",
                        lambda cmd, check=False: subprocess.CompletedProcess(cmd, 1))

    with pytest.raises(SystemExit):
        bootstrap.ensure_deps()

    assert "python3-venv" in capsys.readouterr().out
